# 03 — Gymnasium Environment

## Obiettivo
Costruire l'ambiente RL custom che fa da ponte tra Unciv e Stable-Baselines3.
Deve rispettare l'interfaccia standard `gymnasium.Env`.

---

## Concetti chiave di Gymnasium

Un ambiente Gymnasium deve implementare obbligatoriamente:

| Metodo | Quando viene chiamato | Cosa restituisce |
|---|---|---|
| `reset()` | Inizio episodio | `(observation, info)` |
| `step(action)` | Ad ogni turno | `(obs, reward, terminated, truncated, info)` |
| `render()` | Opzionale, debug | Nulla o immagine |
| `close()` | Fine training | Nulla |

Deve definire obbligatoriamente:

| Attributo | Tipo | Descrizione |
|---|---|---|
| `observation_space` | `gymnasium.Space` | Forma e range delle osservazioni |
| `action_space` | `gymnasium.Space` | Forma e range delle azioni |

---

## Spazio delle Azioni — Fase 1

Per la Fase 1 limitiamo le azioni alla **gestione di una singola città**:

```
Azione 0  → Costruisci Monument
Azione 1  → Costruisci Granary
Azione 2  → Costruisci Library
Azione 3  → Costruisci Barracks
Azione 4  → Costruisci Settler (espandi)
Azione 5  → Costruisci Warrior (unità militare base)
Azione 6  → Fine turno senza costruire
```

`action_space = gymnasium.spaces.Discrete(7)`

---

## Spazio delle Osservazioni — Fase 1

Vettore flat di 7 float normalizzati in `[0, 1]` (dal parser, file 02):

```
[turn/500, gold/1000, happiness/20, n_cities/10, n_techs/80, population/20, n_buildings/20]
```

`observation_space = gymnasium.spaces.Box(low=0.0, high=1.0, shape=(7,), dtype=np.float32)`

---

## Implementazione: `src/envs/unciv_env.py`

```python
import gymnasium as gym
import numpy as np
from pathlib import Path
from typing import Optional
import yaml
import json
import subprocess
import time

from src.parsers.state_parser import UncivStateParser, GameState

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

    def __init__(self, config_path: str = "config/default_config.yaml", render_mode: Optional[str] = None):
        super().__init__()
        self.render_mode = render_mode
        self.config = self._load_config(config_path)
        self.parser = UncivStateParser(player_civ="Romans")
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

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._episode_steps = 0
        self._start_new_game()
        self._current_state = self.parser.parse(self.save_path)
        obs = self.parser.to_observation_vector(self._current_state)
        info = {"turn": self._current_state.turn}
        return obs, info

    def step(self, action: int):
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

        # 4. Calcola reward (vedi file 04)
        reward = self._compute_reward(self._prev_state, self._current_state, action)

        # 5. Controlla terminazione
        terminated = self._is_terminated()
        truncated = self._episode_steps >= self.max_turns

        info = {
            "turn": self._current_state.turn,
            "gold": self._current_state.gold,
            "happiness": self._current_state.happiness,
            "n_cities": len(self._current_state.cities),
        }

        return obs, reward, terminated, truncated, info

    def render(self):
        if self.render_mode == "human":
            s = self._current_state
            print(f"Turn {s.turn} | Gold: {s.gold:.0f} | Happiness: {s.happiness:.0f} | Cities: {len(s.cities)}")

    def close(self):
        pass  # Cleanup se necessario

    # ------------------------------------------------------------------
    # Metodi privati
    # ------------------------------------------------------------------

    def _load_config(self, path: str) -> dict:
        with open(path, 'r') as f:
            return yaml.safe_load(f)

    def _start_new_game(self):
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
        import shutil
        shutil.copy(template_path, self.save_path)

    def _apply_action(self, action: int):
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
            if civ.get("civName") == "Romans":
                if civ.get("cities"):
                    civ["cities"][0]["cityConstructions"]["currentConstruction"] = construction
                break

        with open(self.save_path, 'w') as f:
            json.dump(raw, f)

    def _advance_turn(self):
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

    def _compute_reward(self, prev: GameState, curr: GameState, action: int) -> float:
        """Delega al modulo reward (file 04). STUB qui."""
        return 0.0  # Sostituire con import da src/utils/reward.py

    def _is_terminated(self) -> bool:
        """L'episodio termina se happiness scende sotto soglia critica."""
        if self._current_state is None:
            return False
        return self._current_state.happiness < -10
```

---

## Test: `tests/test_env.py`

```python
import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from src.envs.unciv_env import UncivEnv

@pytest.fixture
def env(tmp_path):
    # Crea config minimale
    config = {
        "training": {"total_timesteps": 1000},
        "environment": {"max_turns": 50, "map_size": "tiny", "victory_type": "science"},
        "paths": {"save_dir": str(tmp_path / "models"), "log_dir": str(tmp_path / "logs"), "unciv_saves": str(tmp_path / "saves")}
    }
    import yaml
    config_path = tmp_path / "config.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(config, f)
    return UncivEnv(config_path=str(config_path))

def test_spaces(env):
    assert env.observation_space.shape == (7,)
    assert env.action_space.n == 7

def test_step_output_shape(env):
    with patch.object(env, '_start_new_game'), \
         patch.object(env, '_apply_action'), \
         patch.object(env, '_advance_turn'), \
         patch.object(env.parser, 'parse') as mock_parse:
        from src.parsers.state_parser import GameState, CityState
        mock_state = GameState(10, "Romans", 200, 5,
            [CityState("Rome", 3, "Monument", [], 200, 0)],
            ["Agriculture"], "Writing", 20, 20)
        mock_parse.return_value = mock_state
        env._current_state = mock_state
        obs, reward, term, trunc, info = env.step(0)
        assert obs.shape == (7,)
        assert isinstance(reward, float)
        assert isinstance(term, bool)
```

---

## Note per Claude Code
- I metodi `_start_new_game`, `_apply_action`, `_advance_turn` sono **STUB espliciti** — nella Fase 1 funzionano con manipolazione JSON diretta, non con Unciv reale
- Il metodo `_compute_reward` deve importare da `src/utils/reward.py` (file 04) — non implementare la logica qui
- La dimensione di `observation_space` **(7,)** deve sempre corrispondere all'output di `parser.to_observation_vector()`
- Usare sempre `gymnasium` (non `gym` vecchio) per compatibilità con Stable-Baselines3 v2+
