import gymnasium as gym
import numpy as np
from pathlib import Path
from typing import Optional
import yaml
import json
import shutil

from src.parsers.state_parser import UncivStateParser, GameState
from src.utils.reward import compute_reward, compute_terminal_reward

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

    def __init__(self, config_path: str = "config/default_config.yaml", render_mode: Optional[str] = None) -> None:
        super().__init__()
        self.render_mode = render_mode
        self.config = self._load_config(config_path)
        self.parser = UncivStateParser(player_civ="India")
        self.save_path = Path(self.config["paths"]["unciv_saves"]) / "current_game.json"
        self.max_turns = self.config["environment"]["max_turns"]

        # Spazi standard Gymnasium
        self.observation_space = gym.spaces.Box(
            low=0.0, high=1.0, shape=(7,), dtype=np.float32
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
        """
        STUB — Fase 1: copia un save file template nella cartella saves/.
        Fase 2+: avvierà Unciv headless per generare una nuova partita.
        """
        template_path = Path("saves/template_game.json")
        if not template_path.exists():
            raise FileNotFoundError(
                "Save template non trovato in saves/template_game.json\n"
                "Genera una partita manuale con Unciv e copiala lì."
            )
        shutil.copy(template_path, self.save_path)

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
        """
        STUB — avanza il turno.
        Fase 1: modifica manuale del counter turni nel JSON.
        Fase 2+: chiama Unciv headless via subprocess.
        """
        with open(self.save_path, 'r') as f:
            raw = json.load(f)
        raw["turns"] = raw.get("turns", 0) + 1
        with open(self.save_path, 'w') as f:
            json.dump(raw, f)

    def _compute_reward(self, prev: Optional[GameState], curr: GameState, action: int) -> float:
        """Delega a src/utils/reward.compute_reward."""
        return compute_reward(prev, curr, action)

    def _is_terminated(self) -> bool:
        """L'episodio termina se happiness scende sotto soglia critica."""
        if self._current_state is None:
            return False
        return bool(self._current_state.happiness < -10)
