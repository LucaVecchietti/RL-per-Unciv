# 10 — Migrazione Observation Space (Fase 2.0 → 2.1)

## Obiettivo

Gestire la transizione dell'observation space da `(7,)` a `(10,)` e action space
da `Discrete(7)` a `Discrete(11)` senza rompere i test esistenti.
Include migrazione da `PPO` a `MaskablePPO` (sb3-contrib).

---

## Il problema della migrazione

Quando si cambia dimensione observation space e action space, tutto si rompe:

```
test_parser.py      → assert obs.shape == (7,)   ← FALLISCE
test_env.py         → assert obs.shape == (7,)   ← FALLISCE
                    → assert env.action_space.n == 7 ← FALLISCE
CLAUDE.md           → contratto (7,) / Discrete(7) ← DA AGGIORNARE
modello Fase 2.0    → input layer size 7          ← INCOMPATIBILE
train.py            → PPO → MaskablePPO           ← DA AGGIORNARE
requirements.txt    → manca sb3-contrib           ← DA AGGIORNARE
```

---

## Ordine di esecuzione — seguire esattamente

```
Step 0  → Copia best model Fase 2.0 con nome esplicito (backup)
Step 1  → Aggiorna requirements.txt (aggiungi sb3-contrib)
Step 2  → pip install sb3-contrib
Step 3  → Aggiorna CLAUDE.md (contratti: (10,) e Discrete(11))
Step 4  → Aggiorna state_parser.py (UnitState, GameState.units, tiles_explored, obs (10,))
Step 5  → Aggiorna test_parser.py (shape (7,) → (10,), GameState mock con units=[])
Step 6  → Verifica: pytest tests/test_parser.py -v      ← deve passare
Step 7  → Aggiorna unciv_env.py (obs space (10,), action space (11), rotation, action_masks)
Step 8  → Aggiorna test_env.py (shape, azioni, test action_masks)
Step 9  → Verifica: pytest tests/test_env.py -v         ← deve passare
Step 10 → Aggiorna reward.py (exploration reward)
Step 11 → Aggiorna test_reward.py (nuovi campi GameState, test exploration)
Step 12 → Verifica: pytest tests/ -v                    ← tutti devono passare
Step 13 → Aggiorna train.py (PPO → MaskablePPO)
Step 14 → Crea tests/test_unit_movement.py (vedi spec 09_unit_movement.md)
Step 15 → Verifica: pytest tests/ -v                    ← tutti devono passare
Step 16 → Aggiorna WORK_LOG.md
Step 17 → git commit -m "feat: Fase 2.1 unit movement (obs 7→10, actions 7→11, MaskablePPO)"
```

**Non procedere allo step successivo se i test falliscono.**

---

## Step 0 — Backup modello Fase 2.0

```powershell
Copy-Item "models\checkpoints\best\best_model.zip" "models\checkpoints\fase2_0_final_model.zip"
```

---

## Step 1 — requirements.txt

Aggiungere:
```
sb3-contrib>=2.0.0
```

---

## Step 3 — Aggiornamenti CLAUDE.md

Nella tabella "Contratti critici tra moduli":

```markdown
| Dimensione observation vector | `(10,)` float32 | `state_parser.py` ↔ `unciv_env.py` |
| Numero azioni                 | `11` (Discrete) | `unciv_env.py` ↔ `train.py`        |
```

Nella sezione "Fasi di sviluppo":

```markdown
- [x] Fase 1   — Gestione singola città
- [x] Fase 1.5 — Micro-simulatore Python
- [x] Fase 2.0 — Headless Unciv integration
- [x] Fase 2.1 — Unit movement (N Warriors + esplorazione)
- [ ] Fase 2.2 — Settler + fondazione città
- [ ] Fase 3   — Combattimento
- [ ] Fase 4   — Diplomazia + vittoria completa
```

---

## Step 4-5 — state_parser.py e test_parser.py

Vedi specifiche complete in `09_unit_movement.md`.

Nei test, ogni occorrenza di:
```python
assert obs.shape == (7,)
```
diventa:
```python
assert obs.shape == (10,)
```

I `GameState` mock devono includere i nuovi campi:
```python
from src.parsers.state_parser import GameState, CityState, UnitState

mock_state = GameState(
    turn=10, current_player="India", gold=200, happiness=5,
    cities=[CityState("Delhi", 3, "Monument", [], 200, 0)],
    techs_researched=["Agriculture"], current_tech="Writing",
    map_width=20, map_height=20,
    units=[],          # nuovo campo Fase 2.1
    tiles_explored=10, # nuovo campo Fase 2.1
)
```

---

## Step 7-8 — unciv_env.py e test_env.py

In `unciv_env.py`:
```python
# Da (Fase 2.0):
self.observation_space = gym.spaces.Box(low=0.0, high=1.0, shape=(7,), dtype=np.float32)
self.action_space = gym.spaces.Discrete(7)

# A (Fase 2.1):
self.observation_space = gym.spaces.Box(low=0.0, high=1.0, shape=(10,), dtype=np.float32)
self.action_space = gym.spaces.Discrete(11)
```

In `test_env.py`:
```python
def test_spaces(env):
    assert env.observation_space.shape == (10,)  # era (7,)
    assert env.action_space.n == 11              # era 7
```

Aggiungere test action_masks (vedi `09_unit_movement.md`).

---

## Step 10-11 — reward.py e test_reward.py

In `test_reward.py`, aggiornare factory `make_state`:

```python
def make_state(
    turn: int = 10,
    gold: float = 200.0,
    happiness: float = 5.0,
    population: int = 3,
    buildings: list[str] = None,
    techs: list[str] = None,
    units: list = None,        # nuovo
    tiles_explored: int = 10,  # nuovo
) -> GameState:
    return GameState(
        turn=turn,
        current_player="India",
        gold=gold,
        happiness=happiness,
        cities=[CityState("Delhi", population, "Monument", buildings or [], 200, 0)],
        techs_researched=techs or ["Agriculture"],
        current_tech="Writing",
        map_width=20,
        map_height=20,
        units=units or [],
        tiles_explored=tiles_explored,
    )
```

Aggiungere:
```python
def test_exploration_reward():
    prev = make_state(tiles_explored=10)
    curr = make_state(tiles_explored=15)
    reward = compute_reward(prev, curr, action=7)
    assert reward == pytest.approx(1.5)  # 5 tile * 0.3
```

---

## Step 13 — train.py: PPO → MaskablePPO

```python
# Da:
from stable_baselines3 import PPO

model = PPO(
    policy="MlpPolicy",
    env=env,
    ...
)

# A:
from sb3_contrib import MaskablePPO

model = MaskablePPO(
    policy="MlpPolicy",
    env=env,
    ...  # tutti gli altri parametri invariati
)
```

`MaskablePPO` chiama `action_masks()` automaticamente — nessuna altra modifica a `train.py`.

---

## Verifica finale post-migrazione

```powershell
# 1. Tutti i test passano
.venv\Scripts\python -m pytest tests/ -v

# 2. Observation vector shape corretta
.venv\Scripts\python -c "
from src.parsers.state_parser import UncivStateParser, GameState, CityState, UnitState
import numpy as np
parser = UncivStateParser()
state = GameState(10, 'India', 200, 5,
    [CityState('Delhi', 3, 'Monument', [], 200, 0)],
    ['Agriculture'], 'Writing', 20, 20,
    units=[], tiles_explored=10)
obs = parser.to_observation_vector(state)
print(f'Shape: {obs.shape}')   # atteso: (10,)
print(f'Dtype: {obs.dtype}')   # atteso: float32
assert obs.shape == (10,), 'ERRORE: shape sbagliata!'
print('OK')
"

# 3. Training avviabile
.venv\Scripts\python -c "from src.envs.unciv_env import UncivEnv; print('Import OK')"
```

---

## Transfer learning da Fase 2.0

Observation space cambia `(7,)→(10,)`: pesi MLP **non compatibili** direttamente.
Non tentare `PPO.load()` con obs space diverso — SB3 lancia errore.

Opzioni:
- **Training da zero** (raccomandato per Fase 2.1): nuovi segnali (esplorazione) cambiano
  abbastanza la task da rendere transfer learning marginale.
- **Partial weight transfer** (avanzato): caricare solo layer interni della policy,
  reinizializzare input/output layer. Documentare in WORK_LOG se si tenta.

---

## Note per Claude Code

- Eseguire `pytest` dopo **ogni singolo step** — non fare tutti gli step e poi verificare
- Se un test fallisce a step N, **fermarsi e correggere** prima di procedere allo step N+1
- Il commit va fatto solo dopo che **tutti gli step** sono completati e tutti i test passano
- Commit message: `feat: Fase 2.1 unit movement (obs 7→10, actions 7→11, MaskablePPO)`
- File 09 (`09_expansion.md`) è ora sostituito da `09_unit_movement.md` — ignorare il vecchio
