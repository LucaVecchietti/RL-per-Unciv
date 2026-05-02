import gymnasium as gym
import numpy as np
from pathlib import Path
from typing import Optional
import yaml
import json

from src.parsers.state_parser import UncivStateParser, GameState
from src.utils.reward import compute_reward, compute_terminal_reward
from src.utils.headless import UncivHeadless

# Mappa azione → nome costruzione Unciv
ACTION_MAP = {
    0: "Monument",
    1: "Granary",
    2: "Library",
    3: "Barracks",
    4: "Settler",
    5: "Warrior",
    6: None,  # Fine turno
}


class UncivEnv(gym.Env):
    """
    Ambiente Gymnasium per Unciv — Fase 1.
    Interfaccia via file JSON: legge stato, scrive azione, avanza turno.
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

        # Spazi standard Gymnasium
        self.observation_space = gym.spaces.Box(
            low=0.0, high=1.0, shape=(48,), dtype=np.float32
        )
        self.action_space = gym.spaces.Discrete(len(ACTION_MAP))

        # Stato interno
        self._current_state: Optional[GameState] = None
        self._prev_state: Optional[GameState] = None
        self._episode_steps = 0

    # ------------------------------------------------------------------
    # Metodi obbligatori Gymnasium
    # ------------------------------------------------------------------

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None) -> tuple[np.ndarray, dict]:
        """Inizia un nuovo episodio. Restituisce (observation, info)."""
        super().reset(seed=seed)
        self._episode_steps = 0
        self._start_new_game()
        self._current_state = self.parser.parse(self.save_path)
        obs = self.parser.to_observation_vector(self._current_state)
        info = {"turn": self._current_state.turn}
        return obs, info

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
        """Esegui un passo: applica azione, avanza turno, restituisce (obs, reward, terminated, truncated, info)."""
        assert self.action_space.contains(action), f"Azione {action} non valida"
        self._prev_state = self._current_state
        self._episode_steps += 1

        # 1. Applica azione → scrivi sul file JSON
        self._apply_action(action)

        # 2. Avanza il turno in Unciv (headless)
        self._advance_turn()

        # 3. Leggi nuovo stato
        self._current_state = self.parser.parse(self.save_path)
        obs = self.parser.to_observation_vector(self._current_state)

        # 4. Calcola reward
        reward = self._compute_reward(self._prev_state, self._current_state, action)

        # 5. Controlla terminazione
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
        Scrive l'azione scelta nel file JSON di Unciv.
        STUB — implementazione dipende dall'interfaccia scelta (JSON / API).
        """
        construction = ACTION_MAP[action]
        if construction is None:
            return  # Fine turno, nessuna modifica

        with open(self.save_path, 'r') as f:
            raw = json.load(f)

        # Modifica currentConstruction nella prima città del giocatore
        for civ in raw.get("civilizations", []):
            if civ.get("civName") == "India":
                if civ.get("cities"):
                    civ["cities"][0]["cityConstructions"]["currentConstruction"] = construction
                break

        with open(self.save_path, 'w') as f:
            json.dump(raw, f)

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
