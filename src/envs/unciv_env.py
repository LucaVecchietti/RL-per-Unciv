import gymnasium as gym
import numpy as np
from pathlib import Path
from typing import Optional
import yaml
import json

from src.parsers.state_parser import UncivStateParser, GameState, UnitState
from src.utils.reward import compute_reward, compute_terminal_reward
from src.utils.headless import UncivHeadless
from src.utils.ruleset_reader import load_early_game_constructions, load_tech_prereqs

# ACTION_MAP built dynamically in __init__ from load_early_game_constructions().
# Order: buildings (alphabetical) → units (alphabetical) → None (skip) → MOVE_*

_MOVE_DELTA: dict[str, tuple[int, int]] = {
    "MOVE_NORTH": (0, 1),
    "MOVE_SOUTH": (0, -1),
    "MOVE_EAST": (1, 0),
    "MOVE_WEST": (-1, 0),
}


class UncivEnv(gym.Env):
    """
    Ambiente Gymnasium per Unciv — Fase 2.2c.

    Action space: Discrete(19) — edifici + unità (da ruleset JAR) + skip + MOVE_*.
    Observation space: Box(57,) float32.
    Per-entity rotation: city step → warrior_0 step → ... → advance turn.
    """

    metadata = {"render_modes": ["human", "rgb_array"]}

    def __init__(
        self,
        config_path: str = "config/default_config.yaml",
        env_rank: int = 0,
        render_mode: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.render_mode = render_mode
        self.config = self._load_config(config_path)
        self.parser = UncivStateParser(player_civ="India")
        self.env_rank = env_rank

        saves_dir = Path(self.config["paths"]["unciv_saves"])
        unciv_cfg = self.config.get("unciv", {})
        prefix = unciv_cfg.get("saves_prefix", "current_game")
        self.save_path = saves_dir / f"{prefix}_{env_rank}.json"
        self.template_path = saves_dir / "template_game.json"
        self.max_turns = self.config["environment"]["max_turns"]

        jar_path = unciv_cfg.get("jar_path", "unciv/Unciv.jar")
        timeout = unciv_cfg.get("headless_timeout", 60)
        java_path = unciv_cfg.get("java_path", "java")
        self.headless = UncivHeadless(jar_path=jar_path, timeout=timeout, java_path=java_path)

        constructions = load_early_game_constructions(jar_path)
        self._prereq_map: dict[str, Optional[str]] = {c.name: c.required_tech for c in constructions}
        self._tech_prereqs: dict[str, list[str]] = load_tech_prereqs(jar_path)
        self._unit_names: set[str] = {c.name for c in constructions if c.is_unit}
        self._building_names: set[str] = {c.name for c in constructions if not c.is_unit}

        buildings = sorted(self._building_names)
        units = sorted(self._unit_names)
        action_list = buildings + units + [None] + ["MOVE_NORTH", "MOVE_SOUTH", "MOVE_EAST", "MOVE_WEST"]
        self.ACTION_MAP: dict[int, Optional[str]] = {i: name for i, name in enumerate(action_list)}
        self._skip_idx: int = action_list.index(None)
        self._move_start_idx: int = self._skip_idx + 1
        self._n_construction_actions: int = len(buildings) + len(units)

        self.observation_space = gym.spaces.Box(
            low=0.0, high=1.0, shape=(57,), dtype=np.float32
        )
        self.action_space = gym.spaces.Discrete(len(self.ACTION_MAP))

        # Stato interno
        self._current_state: Optional[GameState] = None
        self._prev_state: Optional[GameState] = None
        self._episode_steps = 0

        # Per-entity rotation (Fase 2.1)
        self._step_type: str = "city"
        self._unit_rotation_index: int = 0
        self._pending_warriors: list[UnitState] = []
        self._buffered_city_action: int = self._skip_idx

    # ------------------------------------------------------------------
    # Metodi obbligatori Gymnasium
    # ------------------------------------------------------------------

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None) -> tuple[np.ndarray, dict]:
        """Inizia un nuovo episodio. Restituisce (observation, info)."""
        super().reset(seed=seed)
        self._episode_steps = 0
        self._step_type = "city"
        self._unit_rotation_index = 0
        self._pending_warriors = []
        self._buffered_city_action = 6
        self._start_new_game()
        self._current_state = self.parser.parse(self.save_path)
        obs = self._get_obs()
        info = {"turn": self._current_state.turn}
        return obs, info

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
        """
        Esegui un passo con per-entity rotation.

        City step: applica azione costruzione → transizione a unit step se warriors presenti,
                   altrimenti avanza turno direttamente.
        Unit step: applica movimento warrior corrente → avanza turno quando tutti decisi.
        Reward e terminazione calcolati solo al termine del game turn.
        """
        assert self.action_space.contains(action), f"Azione {action} non valida"

        if self._step_type == "city":
            self._buffered_city_action = action
            self._apply_action(action)
            self._pending_warriors = [
                u for u in self._current_state.units
                if u.name == "Warrior" and u.movement_points > 0
            ]
            if self._pending_warriors:
                self._step_type = "unit"
                self._unit_rotation_index = 0
                obs = self._get_obs()
                return obs, 0.0, False, False, {"turn": self._current_state.turn, "step_type": "unit"}
            return self._advance_game_turn()

        # Unit step
        unit = self._pending_warriors[self._unit_rotation_index]
        self._apply_movement(action, unit)
        self._unit_rotation_index += 1

        if self._unit_rotation_index < len(self._pending_warriors):
            obs = self._get_obs()
            return obs, 0.0, False, False, {"turn": self._current_state.turn, "step_type": "unit"}

        self._step_type = "city"
        self._unit_rotation_index = 0
        return self._advance_game_turn()

    def action_masks(self) -> np.ndarray:
        """Maschera azioni valide per MaskablePPO — masking dinamico basato su stato corrente."""
        mask = np.zeros(len(self.ACTION_MAP), dtype=bool)

        if self._step_type == "city":
            if self._current_state is None:
                mask[self._skip_idx] = True
                return mask
            state = self._current_state
            city = state.cities[0] if state.cities else None
            built = set(city.built_buildings) if city else set()
            for i, name in self.ACTION_MAP.items():
                if name is None:
                    mask[i] = True
                elif name.startswith("MOVE_"):
                    mask[i] = False
                else:
                    req = self._prereq_map.get(name)
                    tech_ok = req is None or req in state.techs_researched
                    if name in self._building_names:
                        mask[i] = tech_ok and name not in built
                    else:
                        mask[i] = tech_ok
        elif self._step_type == "unit":
            mask[self._skip_idx] = True
            for i, name in self.ACTION_MAP.items():
                if isinstance(name, str) and name.startswith("MOVE_"):
                    mask[i] = True
        return mask

    def render(self) -> None:
        """Stampa stato corrente in modalità human."""
        if self.render_mode == "human":
            s = self._current_state
            print(f"Turn {s.turn} | Gold: {s.gold:.0f} | Happiness: {s.happiness:.0f} | Cities: {len(s.cities)}")

    def close(self) -> None:
        """Cleanup risorse — spegne il processo JVM persistente."""
        self.headless.close()

    # ------------------------------------------------------------------
    # Metodi privati
    # ------------------------------------------------------------------

    def _load_config(self, path: str) -> dict:
        """Carica config YAML."""
        with open(path, 'r') as f:
            return yaml.safe_load(f)

    def _start_new_game(self) -> None:
        """Crea nuova partita copiando il template via UncivHeadless."""
        self.headless.start_new_game(self.template_path, self.save_path)

    def _apply_action(self, action: int) -> None:
        """Scrive la costruzione scelta nel JSON di Unciv. No-op per skip e MOVE_*."""
        name = self.ACTION_MAP.get(action)
        if name is None or name.startswith("MOVE_"):
            return

        try:
            with open(self.save_path, 'r') as f:
                raw = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return

        for civ in raw.get("civilizations", []):
            if civ.get("civName") == "India":
                if civ.get("cities"):
                    civ["cities"][0]["cityConstructions"]["currentConstruction"] = name
                break

        with open(self.save_path, 'w') as f:
            json.dump(raw, f)

    def _apply_movement(self, action: int, unit: UnitState) -> None:
        """Applica movimento warrior nel JSON (tile swap). No-op per skip e azioni non-MOVE."""
        direction = self.ACTION_MAP.get(action, "")
        delta = _MOVE_DELTA.get(direction, (0, 0))
        if delta == (0, 0):
            return

        try:
            with open(self.save_path, 'r') as f:
                raw = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return

        tile_list = raw.get('tileMap', {}).get('tileList', [])
        new_x, new_y = unit.x + delta[0], unit.y + delta[1]
        src_tile = dst_tile = None
        for tile in tile_list:
            pos = tile.get('position', {})
            tx, ty = int(pos.get('x', -9999)), int(pos.get('y', -9999))
            if tx == unit.x and ty == unit.y:
                src_tile = tile
            if tx == new_x and ty == new_y:
                dst_tile = tile

        if src_tile and dst_tile and 'militaryUnit' in src_tile:
            u_data = src_tile.pop('militaryUnit')
            u_data['currentMovement'] = max(0.0, float(u_data.get('currentMovement', 2.0)) - 1.0)
            dst_tile['militaryUnit'] = u_data
            with open(self.save_path, 'w') as f:
                json.dump(raw, f)

    def _advance_game_turn(self) -> tuple[np.ndarray, float, bool, bool, dict]:
        """Avanza turno Unciv, calcola reward, restituisce output step."""
        self._prev_state = self._current_state
        self._episode_steps += 1
        self._ensure_tech_queued()
        self._advance_turn()
        self._current_state = self.parser.parse(self.save_path)
        obs = self._get_obs()
        reward = self._compute_reward(self._prev_state, self._current_state, self._buffered_city_action)
        terminated = self._is_terminated()
        truncated = self._episode_steps >= self.max_turns
        if terminated:
            reward += compute_terminal_reward(self._current_state, self.max_turns)
        info = {
            "turn": self._current_state.turn,
            "gold": self._current_state.gold,
            "happiness": self._current_state.happiness,
            "n_cities": len(self._current_state.cities),
            "n_techs": len(self._current_state.techs_researched),
            "population": sum(c.population for c in self._current_state.cities),
        }
        return obs, reward, terminated, truncated, info

    def _get_obs(self) -> np.ndarray:
        """Restituisce obs con unità selezionata se in unit step."""
        selected: Optional[UnitState] = None
        if (self._step_type == "unit" and self._pending_warriors and
                self._unit_rotation_index < len(self._pending_warriors)):
            selected = self._pending_warriors[self._unit_rotation_index]
        return self.parser.to_observation_vector(self._current_state, selected_unit=selected)

    def _ensure_tech_queued(self) -> None:
        """Auto-select a tech if no research is queued, preventing science waste."""
        try:
            with open(self.save_path, 'r') as f:
                raw = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return

        for civ in raw.get("civilizations", []):
            if civ.get("civName") != "India":
                continue
            tech = civ.get("tech", {})
            if tech.get("currentTechResearch"):
                return
            researched = set(tech.get("techsResearched") or [])
            chosen = next(
                (t for t, prereqs in sorted(self._tech_prereqs.items())
                 if t not in researched and all(p in researched for p in prereqs)),
                None,
            )
            if chosen is None:
                return
            tech["currentTechResearch"] = chosen
            if not tech.get("techsInProgress"):
                tech["techsInProgress"] = {chosen: 0}
            civ["tech"] = tech
            break

        with open(self.save_path, 'w') as f:
            json.dump(raw, f)

    def _advance_turn(self) -> None:
        """Fase 2.0: avanza turno via Unciv headless."""
        self.headless.advance_turn(self.save_path)

    def _compute_reward(self, prev: Optional[GameState], curr: GameState, action: int) -> float:
        """Delega a src/utils/reward.compute_reward."""
        return compute_reward(prev, curr, action, skip_action_idx=self._skip_idx)

    def _is_terminated(self) -> bool:
        """L'episodio termina se happiness scende sotto soglia critica."""
        if self._current_state is None:
            return False
        return bool(self._current_state.happiness < -10)
