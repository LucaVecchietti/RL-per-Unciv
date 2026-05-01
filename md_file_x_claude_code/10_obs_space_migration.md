# 10 — Migrazione Observation Space (Fase 1 → Fase 2)

## Obiettivo
Gestire la transizione dell'observation space da (7,) a (12,) senza perdere
il lavoro fatto nella Fase 1 e mantenendo tutti i test verdi.

---

## Il problema della migrazione

Quando si cambia la dimensione dell'observation space, **tutto si rompe**:

```
test_parser.py      → assert obs.shape == (7,)   ← FALLISCE
test_env.py         → assert obs.shape == (7,)   ← FALLISCE
CLAUDE.md           → contratto (7,)              ← DA AGGIORNARE
modello Fase 1      → input layer size 7          ← INCOMPATIBILE
```

Bisogna aggiornare tutto in modo coordinato e nell'ordine corretto.

---

## Ordine di esecuzione — seguire esattamente

```
Step 1 → Aggiorna CLAUDE.md (contratto)
Step 2 → Aggiorna state_parser.py (nuovi campi + nuovo vettore)
Step 3 → Aggiorna test_parser.py (shape 7 → 12)
Step 4 → Verifica: pytest tests/test_parser.py -v  ← deve passare
Step 5 → Aggiorna unciv_env.py (nuovo observation_space + nuove azioni)
Step 6 → Aggiorna test_env.py (shape 7 → 12, n azioni 7 → 9)
Step 7 → Verifica: pytest tests/test_env.py -v     ← deve passare
Step 8 → Aggiorna reward.py (nuovi componenti)
Step 9 → Aggiorna test_reward.py (nuovi stati con campi Fase 2)
Step 10 → Verifica: pytest tests/ -v               ← tutti devono passare
Step 11 → Aggiorna WORK_LOG.md
Step 12 → git commit -m "feat: observation space Fase 2 (7,) → (12,)"
```

**Non procedere allo step successivo se i test falliscono.**

---

## Step 1 — Aggiornamenti CLAUDE.md

Nella tabella "Contratti critici tra moduli" aggiornare:

```markdown
| Dimensione observation vector | `(12,)` float32 | `state_parser.py` ↔ `unciv_env.py` |
| Numero azioni                 | `9` (Discrete)  | `unciv_env.py` ↔ `train.py`        |
```

Nella sezione "Fasi di sviluppo" aggiornare:

```markdown
- [x] **Fase 1** — Gestione singola città (produzione, tech, oro, happiness)
- [x] **Fase 2** — Espansione (settler, esplorazione mappa) ← quando completata
- [ ] **Fase 3** — Combattimento (unità militari)
- [ ] **Fase 4** — Diplomazia + vittoria completa
```

---

## Step 2-3 — Aggiornamenti state_parser.py e test_parser.py

Vedere specifiche complete in `09_expansion.md`.

Nelle modifiche ai test, ogni occorrenza di:
```python
assert obs.shape == (7,)
```
diventa:
```python
assert obs.shape == (12,)
```

E i `GameState` mock devono includere i nuovi campi:
```python
from src.parsers.state_parser import GameState, CityState, UnitState

mock_state = GameState(
    turn=10, current_player="India", gold=200, happiness=5,
    cities=[CityState("Delhi", 3, "Monument", [], 200, 0)],
    techs_researched=["Agriculture"], current_tech="Writing",
    map_width=20, map_height=20,
    units=[],           # nuovo campo Fase 2
    tiles_explored=10,  # nuovo campo Fase 2
)
```

---

## Step 5-6 — Aggiornamenti unciv_env.py e test_env.py

In `unciv_env.py`:
```python
# Da
self.observation_space = gym.spaces.Box(low=0.0, high=1.0, shape=(7,), dtype=np.float32)
self.action_space = gym.spaces.Discrete(7)

# A
self.observation_space = gym.spaces.Box(low=0.0, high=1.0, shape=(12,), dtype=np.float32)
self.action_space = gym.spaces.Discrete(9)
```

In `test_env.py`:
```python
def test_spaces(env):
    assert env.observation_space.shape == (12,)  # era (7,)
    assert env.action_space.n == 9               # era 7
```

---

## Step 7-8 — Aggiornamenti reward.py e test_reward.py

In `test_reward.py`, aggiornare la factory `make_state`:

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

Aggiungere test per i nuovi componenti reward:

```python
def test_new_city_reward():
    prev = make_state()  # 1 città
    # Simula 2 città nel curr
    curr_state = make_state()
    from src.parsers.state_parser import CityState
    curr_state.cities.append(CityState("Bombay", 1, "", [], 200, 0))
    reward = compute_reward(prev, curr_state, action=7)
    assert reward >= REWARD_WEIGHTS["new_city"]


def test_exploration_reward():
    prev = make_state(tiles_explored=10)
    curr = make_state(tiles_explored=15)
    reward = compute_reward(prev, curr, action=8)
    assert reward > 0.0
```

---

## Salvataggio modello Fase 1 prima della migrazione

**Importante:** prima di modificare qualsiasi file, salvare il modello Fase 1:

```powershell
# Copia il best model Fase 1 con nome esplicito
Copy-Item "models\checkpoints\best\best_model.zip" "models\checkpoints\fase1_final_model.zip"
```

Questo file servirà come punto di partenza per il transfer learning (anche se
l'observation space cambia e i pesi non sono direttamente riusabili, è utile
tenerlo come riferimento delle performance baseline).

---

## Verifica finale post-migrazione

```powershell
# 1. Tutti i test passano
.venv\Scripts\python -m pytest tests/ -v

# 2. L'observation vector ha la shape corretta
.venv\Scripts\python -c "
from src.parsers.state_parser import UncivStateParser, GameState, CityState, UnitState
import numpy as np
parser = UncivStateParser()
state = GameState(10, 'India', 200, 5,
    [CityState('Delhi', 3, 'Monument', [], 200, 0)],
    ['Agriculture'], 'Writing', 20, 20,
    units=[], tiles_explored=10)
obs = parser.to_observation_vector(state)
print(f'Shape: {obs.shape}')   # atteso: (12,)
print(f'Dtype: {obs.dtype}')   # atteso: float32
assert obs.shape == (12,), 'ERRORE: shape sbagliata!'
print('OK - migrazione completata')
"

# 3. Training avviabile senza errori
.venv\Scripts\python -c "from src.envs.unciv_env import UncivEnv; print('Import OK')"
```

---

## Note per Claude Code
- Eseguire `pytest` dopo **ogni singolo step** — non fare tutti gli step e poi verificare
- Se un test fallisce a step N, **fermarsi e correggere** prima di procedere allo step N+1
- Il commit va fatto solo dopo che **tutti i 10 step** sono completati e tutti i test passano
- Il messaggio di commit deve essere: `feat: observation space Fase 2 (7,) → (12,)`
- Aggiornare `WORK_LOG.md` documentando ogni step completato con output pytest
