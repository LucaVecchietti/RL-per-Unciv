import gymnasium as gym
import numpy as np
from pathlib import Path
from typing import Optional
import yaml
import json

from src.parsers.state_parser import UncivStateParser, GameState, UnitState, _TECH_COSTS
from src.utils.reward import compute_reward, compute_terminal_reward
from src.utils.headless import UncivHeadless
from src.utils.ruleset_reader import (
    load_early_game_constructions,
    load_tech_prereqs,
    load_resource_types,
    load_resource_improvements,
)

# ACTION_MAP built dynamically in __init__ from load_early_game_constructions().
# Order: buildings (alphabetical) → units (alphabetical) → None (skip) → MOVE_*

# 6 vicini esagonali — clock positions di HexMath. L'azione MOVE_<c> muove di una casella.
_MOVE_CLOCKS = [2, 4, 6, 8, 10, 12]


def _count_by_name(units: list[UnitState]) -> dict[str, int]:
    """Conta le unità per nome. Usato per il delta unità create per-episodio."""
    counts: dict[str, int] = {}
    for u in units:
        counts[u.name] = counts.get(u.name, 0) + 1
    return counts


class UncivEnv(gym.Env):
    """
    Ambiente Gymnasium per Unciv — Fase 2.C (espansione + risorse).

    Action space: Discrete(23) — edifici + unità + skip + 6 direzioni hex + FoundCity + Improve.
    Observation space: Box(61,) float32 (Città1 = città selezionata; +4 feature risorse C2).
    Per-entity rotation: città_0 step → … → unità_0 step → … → advance turn.
    Movimento e fondazione città delegati al motore Unciv.
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
        # File 22 (C2/C3) — mappe risorsa→tipo e risorsa→miglioramento dal ruleset
        self.parser.resource_types = load_resource_types(jar_path)
        self.parser.resource_improvements = load_resource_improvements(jar_path)
        self._prereq_map: dict[str, Optional[str]] = {c.name: c.required_tech for c in constructions}
        self._tech_prereqs: dict[str, list[str]] = load_tech_prereqs(jar_path)
        self._unit_names: set[str] = {c.name for c in constructions if c.is_unit}
        self._building_names: set[str] = {c.name for c in constructions if not c.is_unit}

        buildings = sorted(self._building_names)
        units = sorted(self._unit_names)
        move_names = [f"MOVE_{c}" for c in _MOVE_CLOCKS]
        action_list = buildings + units + [None] + move_names + ["FoundCity", "Improve"]
        self.ACTION_MAP: dict[int, Optional[str]] = {i: name for i, name in enumerate(action_list)}
        self._skip_idx: int = action_list.index(None)
        self._move_start_idx: int = self._skip_idx + 1
        self._found_city_idx: int = action_list.index("FoundCity")
        self._improve_idx: int = action_list.index("Improve")
        self._n_construction_actions: int = len(buildings) + len(units)
        # mappa indice azione → direzione hex (clock)
        self._action_to_clock: dict[int, int] = {
            self._move_start_idx + i: c for i, c in enumerate(_MOVE_CLOCKS)
        }

        self.observation_space = gym.spaces.Box(
            low=0.0, high=1.0, shape=(61,), dtype=np.float32
        )
        self.action_space = gym.spaces.Discrete(len(self.ACTION_MAP))

        # Stato interno
        self._current_state: Optional[GameState] = None
        self._prev_state: Optional[GameState] = None
        self._episode_steps = 0

        # Per-entity rotation (Fase 2.1 / 2.B / 2.C — città e unità)
        self._step_type: str = "city"
        self._city_rotation_index: int = 0
        self._pending_cities: list = []
        self._unit_rotation_index: int = 0
        self._pending_units: list[UnitState] = []
        self._buffered_city_action: int = self._skip_idx

        # File 19 — contatori metriche per-episodio
        self._ep_total_gold: float = 0.0
        self._ep_total_science: float = 0.0
        self._ep_total_culture: float = 0.0
        self._ep_buildings_built: dict[str, int] = {}
        self._ep_units_built: dict[str, int] = {}

        # File 21 — metriche movimento per-episodio
        self._ep_moves_attempted: int = 0
        self._ep_moves_succeeded: int = 0
        self._ep_moves_illegal: int = 0
        self._ep_move_cost_total: float = 0.0
        self._ep_moved_by_type: dict[str, int] = {}
        self._ep_legal_moves_total: int = 0
        self._ep_legal_moves_count: int = 0
        self._ep_units_stuck: int = 0
        self._ep_new_tiles: int = 0

        # File 22 (C1/C3) — espansione e miglioramenti
        self._ep_cities_founded: int = 0
        self._ep_improvements_built: int = 0

    # ------------------------------------------------------------------
    # Metodi obbligatori Gymnasium
    # ------------------------------------------------------------------

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None) -> tuple[np.ndarray, dict]:
        """Inizia un nuovo episodio. Restituisce (observation, info)."""
        super().reset(seed=seed)
        self._episode_steps = 0
        self._step_type = "city"
        self._city_rotation_index = 0
        self._pending_cities = []
        self._unit_rotation_index = 0
        self._pending_units = []
        self._buffered_city_action = 6
        self._ep_total_gold = 0.0
        self._ep_total_science = 0.0
        self._ep_total_culture = 0.0
        self._ep_buildings_built = {}
        self._ep_units_built = {}
        self._ep_moves_attempted = 0
        self._ep_moves_succeeded = 0
        self._ep_moves_illegal = 0
        self._ep_move_cost_total = 0.0
        self._ep_moved_by_type = {}
        self._ep_legal_moves_total = 0
        self._ep_legal_moves_count = 0
        self._ep_units_stuck = 0
        self._ep_new_tiles = 0
        self._ep_cities_founded = 0
        self._ep_improvements_built = 0
        self._start_new_game()
        self._current_state = self.parser.parse(self.save_path)
        self._pending_cities = list(self._current_state.cities)
        self._city_rotation_index = 0
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
            self._apply_action(action, self._city_rotation_index)
            self._city_rotation_index += 1
            if self._city_rotation_index < len(self._pending_cities):
                obs = self._get_obs()
                return obs, 0.0, False, False, {"turn": self._current_state.turn, "step_type": "city"}
            # tutte le città decise → fase unità
            self._pending_units = [
                u for u in self._current_state.units
                if u.movement_points > 0
            ]
            if self._pending_units:
                self._step_type = "unit"
                self._unit_rotation_index = 0
                obs = self._get_obs()
                return obs, 0.0, False, False, {"turn": self._current_state.turn, "step_type": "unit"}
            return self._advance_game_turn()

        # Unit step
        unit = self._pending_units[self._unit_rotation_index]
        if action == self._found_city_idx:
            self._apply_found_city(unit)
        elif action == self._improve_idx:
            self._apply_improve(unit)
        else:
            self._apply_movement(action, unit)
        self._unit_rotation_index += 1

        if self._unit_rotation_index < len(self._pending_units):
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
            # città selezionata nella rotation per-città
            city = None
            if self._pending_cities and self._city_rotation_index < len(self._pending_cities):
                city = self._pending_cities[self._city_rotation_index]
            elif state.cities:
                city = state.cities[0]
            built = set(city.built_buildings) if city else set()
            for i, name in self.ACTION_MAP.items():
                if name is None:
                    mask[i] = True
                elif name == "FoundCity" or name == "Improve" or name.startswith("MOVE_"):
                    mask[i] = False
                else:
                    req = self._prereq_map.get(name)
                    tech_ok = req is None or req in state.techs_researched
                    if name in self._building_names:
                        mask[i] = tech_ok and name not in built
                    else:
                        mask[i] = tech_ok
        elif self._step_type == "unit":
            mask[self._skip_idx] = True  # skip sempre valido (anti-deadlock)
            unit = None
            if self._pending_units and self._unit_rotation_index < len(self._pending_units):
                unit = self._pending_units[self._unit_rotation_index]
            if unit is not None and unit.id >= 0:
                legal = self.headless.legal_moves(self.save_path, unit.id)
                self._ep_legal_moves_total += len(legal)
                self._ep_legal_moves_count += 1
                if not legal:
                    self._ep_units_stuck += 1
                for i, clock in self._action_to_clock.items():
                    if clock in legal:
                        mask[i] = True
                # FoundCity valido solo per i Settler
                if unit.name == "Settler":
                    mask[self._found_city_idx] = True
                # Improve valido solo per i Worker
                if unit.name == "Worker":
                    mask[self._improve_idx] = True
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

    def _apply_action(self, action: int, city_index: int = 0) -> None:
        """Scrive la costruzione scelta nella città `city_index`. No-op per skip, MOVE_* e FoundCity."""
        name = self.ACTION_MAP.get(action)
        if name is None or name == "FoundCity" or name.startswith("MOVE_"):
            return

        try:
            with open(self.save_path, 'r') as f:
                raw = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return

        for civ in raw.get("civilizations", []):
            if civ.get("civName") == "India":
                cities = civ.get("cities")
                if cities and city_index < len(cities):
                    cc = cities[city_index].setdefault("cityConstructions", {})
                    cc["constructionQueue"] = [name]
                    cc.setdefault("inProgressConstructions", {})
                    cc["currentConstructionIsUserSet"] = True
                    cc.pop("currentConstruction", None)
                break

        with open(self.save_path, 'w') as f:
            json.dump(raw, f)

    def _apply_movement(self, action: int, unit: UnitState) -> None:
        """Muove l'unità via il server headless (clock-based, costo terreno reale). No-op per skip."""
        clock = self._action_to_clock.get(action)
        if clock is None:
            return  # skip o azione non di movimento
        if unit.id < 0:
            return
        self._ep_moves_attempted += 1
        result = self.headless.move_unit(self.save_path, unit.id, clock)
        if result.get("success"):
            self._ep_moves_succeeded += 1
            cost = max(0.0, unit.movement_points - float(result.get("movement_left", 0.0)))
            self._ep_move_cost_total += cost
            self._ep_moved_by_type[unit.name] = self._ep_moved_by_type.get(unit.name, 0) + 1
        else:
            self._ep_moves_illegal += 1

    def _apply_found_city(self, unit: UnitState) -> None:
        """Fonda una città col Settler selezionato via il server headless. No-op se fallisce."""
        if unit.id < 0:
            return
        result = self.headless.found_city(self.save_path, unit.id)
        if result.get("success"):
            self._ep_cities_founded += 1

    def _apply_improve(self, unit: UnitState) -> None:
        """Fa costruire al Worker il miglioramento che connette la risorsa sul tile. No-op se fallisce."""
        if unit.id < 0:
            return
        result = self.headless.build_improvement(self.save_path, unit.id)
        if result.get("success"):
            self._ep_improvements_built += 1

    def _advance_game_turn(self) -> tuple[np.ndarray, float, bool, bool, dict]:
        """Avanza turno Unciv, calcola reward, restituisce output step."""
        self._prev_state = self._current_state
        self._episode_steps += 1
        self._advance_turn()
        self._advance_tech()
        self._current_state = self.parser.parse(self.save_path)
        prev = self._prev_state
        curr = self._current_state
        # Cultura/turno = delta di stored_culture (il parser non ha lo stato precedente)
        if prev is not None:
            curr.culture_per_turn = max(0.0, curr.stored_culture - prev.stored_culture)
        self._accumulate_episode_metrics(prev, curr)
        # nuovo turno → fase città (rotation per-città su tutte le città)
        self._step_type = "city"
        self._pending_cities = list(curr.cities)
        self._city_rotation_index = 0
        obs = self._get_obs()
        reward = self._compute_reward(prev, curr, self._buffered_city_action)
        terminated = self._is_terminated()
        truncated = self._episode_steps >= self.max_turns
        if terminated:
            reward += compute_terminal_reward(curr, self.max_turns)
        info = {
            "turn": curr.turn,
            "gold": curr.gold,
            "happiness": curr.happiness,
            "n_cities": len(curr.cities),
            "n_techs": len(curr.techs_researched),
            "population": sum(c.population for c in curr.cities),
            # File 19 — metriche estese
            "tiles_explored": curr.tiles_explored,
            "city_territory_tiles": curr.city_territory_tiles,
            "science_per_turn": curr.science_per_turn,
            "culture_per_turn": curr.culture_per_turn,
            "strategic_resources": dict(curr.strategic_resources),
            "luxury_resources": dict(curr.luxury_resources),
            "ep_total_gold": self._ep_total_gold,
            "ep_total_science": self._ep_total_science,
            "ep_total_culture": self._ep_total_culture,
            "ep_buildings_built": dict(self._ep_buildings_built),
            "ep_units_built": dict(self._ep_units_built),
            # File 21 — metriche movimento
            "moves_attempted": self._ep_moves_attempted,
            "moves_succeeded": self._ep_moves_succeeded,
            "moves_illegal": self._ep_moves_illegal,
            "move_cost_mean": (self._ep_move_cost_total / self._ep_moves_succeeded) if self._ep_moves_succeeded else 0.0,
            "moved_by_type": dict(self._ep_moved_by_type),
            "units_stuck": self._ep_units_stuck,
            "legal_moves_available": (self._ep_legal_moves_total / self._ep_legal_moves_count) if self._ep_legal_moves_count else 0.0,
            "new_tiles_per_move": (self._ep_new_tiles / self._ep_moves_succeeded) if self._ep_moves_succeeded else 0.0,
            # File 22 (C1) — espansione
            "cities_founded": self._ep_cities_founded,
            # File 22 (C2) — risorse nel territorio (Strategic + Luxury, tutte le città)
            "territory_resources": sum(c.territory_strategic + c.territory_luxury for c in curr.cities),
            # File 22 (C3) — miglioramenti e risorse connesse
            "improvements_built": self._ep_improvements_built,
            "connected_resources": curr.connected_strategic + curr.connected_luxury,
        }
        return obs, reward, terminated, truncated, info

    def _accumulate_episode_metrics(self, prev: Optional[GameState], curr: GameState) -> None:
        """Aggiorna i contatori per-episodio (File 19) confrontando stato precedente e corrente."""
        if prev is not None:
            self._ep_total_gold += max(0.0, curr.gold - prev.gold)
            self._ep_new_tiles += max(0, curr.tiles_explored - prev.tiles_explored)
        self._ep_total_science += curr.science_per_turn
        self._ep_total_culture += curr.culture_per_turn
        if prev is None:
            return
        prev_built = {b for c in prev.cities for b in c.built_buildings}
        curr_built = {b for c in curr.cities for b in c.built_buildings}
        for b in curr_built - prev_built:
            self._ep_buildings_built[b] = self._ep_buildings_built.get(b, 0) + 1
        prev_unit_counts = _count_by_name(prev.units)
        curr_unit_counts = _count_by_name(curr.units)
        for name, cnt in curr_unit_counts.items():
            delta = max(0, cnt - prev_unit_counts.get(name, 0))
            if delta:
                self._ep_units_built[name] = self._ep_units_built.get(name, 0) + delta

    def _get_obs(self) -> np.ndarray:
        """Restituisce obs con entità selezionata: città in city step, unità in unit step."""
        selected_unit: Optional[UnitState] = None
        selected_city = None
        if (self._step_type == "unit" and self._pending_units and
                self._unit_rotation_index < len(self._pending_units)):
            selected_unit = self._pending_units[self._unit_rotation_index]
        elif (self._step_type == "city" and self._pending_cities and
                self._city_rotation_index < len(self._pending_cities)):
            selected_city = self._pending_cities[self._city_rotation_index]
        return self.parser.to_observation_vector(
            self._current_state, selected_unit=selected_unit, selected_city=selected_city
        )

    def _advance_tech(self) -> None:
        """Manually accumulate science for player civ (JVM skips player tech in headless)."""
        try:
            with open(self.save_path, 'r') as f:
                raw = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return

        for civ in raw.get("civilizations", []):
            if civ.get("civName") != "India":
                continue
            tech = civ.get("tech", {})
            science_history = tech.get("scienceOfLast8Turns") or []
            science = float(science_history[-1]) if science_history else 0.0
            if science <= 0:
                break

            researched = set(tech.get("techsResearched") or [])
            in_progress = dict(tech.get("techsInProgress") or {})
            current = next(iter(in_progress), None)
            if not current:
                current = next(
                    (t for t, prereqs in sorted(self._tech_prereqs.items())
                     if t not in researched and all(p in researched for p in prereqs)),
                    None,
                )
                if not current:
                    break
                in_progress = {current: 0.0}

            in_progress[current] = in_progress.get(current, 0.0) + science
            cost = float(_TECH_COSTS.get(current, 60.0))
            if in_progress[current] >= cost:
                overflow = in_progress.pop(current) - cost
                researched.add(current)
                tech["techsResearched"] = sorted(researched)
                next_tech = next(
                    (t for t, prereqs in sorted(self._tech_prereqs.items())
                     if t not in researched and all(p in researched for p in prereqs)),
                    None,
                )
                in_progress = {next_tech: max(0.0, overflow)} if next_tech else {}

            tech["techsInProgress"] = dict(in_progress) or None
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
