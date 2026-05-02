import gymnasium as gym
import numpy as np
from pathlib import Path
from typing import Optional
import yaml
import json

from src.parsers.state_parser import UncivStateParser, GameState, UnitState
from src.utils.reward import compute_reward, compute_terminal_reward
from src.utils.headless import UncivHeadless

# Fase 2.1: azioni 0-6 costruzione città, 7-10 movimento warrior
ACTION_MAP = {
    0: "Monument",
    1: "Granary",
    2: "Library",
    3: "Barracks",
    4: "Settler",
    5: "Warrior",
    6: None,         # Fine turno / skip
    7: "MOVE_NORTH",
    8: "MOVE_SOUTH",
    9: "MOVE_EAST",
    10: "MOVE_WEST",
}

_MOVE_DELTA: dict[str, tuple[int, int]] = {
    "MOVE_NORTH": (0, 1),
    "MOVE_SOUTH": (0, -1),
    "MOVE_EAST": (1, 0),
    "MOVE_WEST": (-1, 0),
}


class UncivEnv(gym.Env):
    """
    Ambiente Gymnasium per Unciv — Fase 2.1.

    Action space: Discrete(11) — costruzione città (0-6) + movimento warrior (7-10).
    Observation space: Box(52,) float32.
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

        self.observation_space = gym.spaces.Box(
            low=0.0, high=1.0, shape=(52,), dtype=np.float32
        )
        self.action_space = gym.spaces.Discrete(len(ACTION_MAP))

        # Stato interno
        self._current_state: Optional[GameState] = None
        self._prev_state: Optional[GameState] = None
        self._episode_steps = 0

        # Per-entity rotation (Fase 2.1)
        self._step_type: str = "city"
        self._unit_rotation_index: int = 0
        self._pending_warriors: list[UnitState] = []
        self._buffered_city_action: int = 6

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
        """Maschera azioni valide per MaskablePPO."""
        mask = np.zeros(11, dtype=bool)
        if self._step_type == "city":
            mask[0:7] = True
        elif self._step_type == "unit":
            mask[6] = True     # skip
            mask[7:11] = True  # movimento
        return mask

    def render(self) -> None:
        """Stampa stato corrente in modalità human."""
        if self.render_mode == "human":
            s = self._current_state
            print(f"Turn {s.turn} | Gold: {s.gold:.0f} | Happiness: {s.happiness:.0f} | Cities: {len(s.cities)}")

    def close(self) -> None:
        """Cleanup risorse."""
        pass

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
        """
        Scrive l'azione costruzione (0-6) nel JSON di Unciv.
        Ignorata per azioni di movimento (7-10).
        """
        if action >= 7:
            return
        construction = ACTION_MAP[action]
        if construction is None:
            return

        try:
            with open(self.save_path, 'r') as f:
                raw = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return

        for civ in raw.get("civilizations", []):
            if civ.get("civName") == "India":
                if civ.get("cities"):
                    civ["cities"][0]["cityConstructions"]["currentConstruction"] = construction
                break

        with open(self.save_path, 'w') as f:
            json.dump(raw, f)

    def _apply_movement(self, action: int, unit: UnitState) -> None:
        """
        Applica movimento warrior nel JSON spostando l'unità sulla tile di destinazione.
        Azione 6 (skip) non modifica il JSON.
        """
        if action == 6:
            return
        direction = ACTION_MAP.get(action, "")
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
        }
        return obs, reward, terminated, truncated, info

    def _get_obs(self) -> np.ndarray:
        """Restituisce obs con unità selezionata se in unit step."""
        selected: Optional[UnitState] = None
        if (self._step_type == "unit" and self._pending_warriors and
                self._unit_rotation_index < len(self._pending_warriors)):
            selected = self._pending_warriors[self._unit_rotation_index]
        return self.parser.to_observation_vector(self._current_state, selected_unit=selected)

    def _advance_turn(self) -> None:
        """Fase 2.0: avanza turno via Unciv headless."""
        self.headless.advance_turn(self.save_path)

    def _compute_reward(self, prev: Optional[GameState], curr: GameState, action: int) -> float:
        """Delega a src/utils/reward.compute_reward."""
        return compute_reward(prev, curr, action)

    def _is_terminated(self) -> bool:
        """L'episodio termina se happiness scende sotto soglia critica."""
        if self._current_state is None:
            return False
        return bool(self._current_state.happiness < -10)
