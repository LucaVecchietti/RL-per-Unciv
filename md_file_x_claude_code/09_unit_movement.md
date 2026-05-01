# 09 — Unit Movement (Fase 2.1)

## Obiettivo

Agente impara il loop completo: **costruisci unità → muovila → esplora mappa**.
Prerequisito obbligatorio per Fase 2.2 (Settler + fondazione città): agente deve
padroneggiare il meccanismo di movimento prima di usarlo per decisioni strategiche.

**Prerequisito:** Fase 2.0 (headless integration) completata e training stabile.

---

## Cosa cambia rispetto a Fase 2.0

| Componente | Fase 2.0 | Fase 2.1 |
|---|---|---|
| Action space | `Discrete(7)` | `Discrete(11)` |
| Observation | `(7,)` | `(10,)` |
| Unità | 0 | N Warrior (build-first) |
| Movimento | — | 1 tile/turno (N/S/E/W) |
| Per-turn decisions | 1 (costruzione) | 1+N (costruzione + N warriors) |
| PPO | standard | MaskablePPO (sb3-contrib) |

---

## Design: N Warriors, Build-First

Warrior non è pre-built nel template — l'agente deve costruirlo (action 5).
Questo insegna il loop completo: riconosci bisogno → costruisci → usa.

Numero di Warrior: illimitato. Agente sceglie quanti costruirne.
Constraint organico: ogni Warrior costruito = ~13 turni di produzione non usati per
Monument/Granary → happiness/pop sacrifice. Agente bilancia autonomamente.

---

## Nuovo spazio delle azioni — `Discrete(11)`

```python
ACTION_MAP = {
    # Fase 2.0 — invariate (costruzione città)
    0: "Monument",
    1: "Granary",
    2: "Library",
    3: "Barracks",
    4: "Settler",    # deferred a Fase 2.2 — azione esiste ma non usata in 2.1
    5: "Warrior",
    6: None,         # END_TURN / skip (città o unità corrente)

    # Fase 2.1 — movimento unità
    7: "MOVE_NORTH",
    8: "MOVE_SOUTH",
    9: "MOVE_EAST",
    10: "MOVE_WEST",
}
```

---

## Design: Per-Entity Rotation

Ogni game turn = sequenza di step fino a che tutte le decisioni sono prese.

```
Rotation order ogni turno:
  1. City decision step:
       obs = stato città + n_warriors + warrior_corrente=None
       azioni valide: [0-6]
       agente sceglie cosa costruire (o END_TURN per città)

  2. Warrior_0 decision step (se warrior_0 esiste con MP > 0):
       obs = stato città + n_warriors + posizione warrior_0
       azioni valide: [6, 7, 8, 9, 10]  (skip o direzione)
       agente sceglie dove muovere

  3. Warrior_1 decision step (se warrior_1 esiste con MP > 0):
       ... stessa logica ...

  N. Tutti i warrior hanno deciso → turno avanza automaticamente
```

Agente non sceglie quale warrior muovere — il sistema li presenta in ordine.
Agente vede posizione del warrior corrente nell'observation.

---

## Nuovo spazio delle osservazioni — `(10,)` float32

```
[0] turn / max_turns
[1] gold / 1000
[2] happiness / 20
[3] n_techs / 80
[4] city.population / 20
[5] city.n_buildings / 20

# Nuovi Fase 2.1
[6] n_warriors / 10                ← quanti Warrior esistono
[7] selected_warrior_x / map_w    ← warrior corrente (0.0 se city step)
[8] selected_warrior_y / map_h    ← warrior corrente (0.0 se city step)
[9] tiles_explored / total_tiles  ← percentuale mappa esplorata
```

`has_warrior` non serve come flag separato: agente capisce dal contesto che
se `n_warriors == 0.0` non ci sono step warrior, e in city step `[7],[8] == 0.0`.

> **Contratto:** shape `(10,)` float32, valori in `[0, ~1]`.
> Aggiornare tabella in `CLAUDE.md`.

---

## Action Masking — `MaskablePPO`

Usare `sb3-contrib` invece di `PPO` standard:

```python
from sb3_contrib import MaskablePPO

model = MaskablePPO(
    policy="MlpPolicy",
    env=env,
    learning_rate=tc["learning_rate"],
    # ... altri parametri invariati ...
)
```

L'env deve implementare `action_masks() -> np.ndarray[bool]`:

```python
def action_masks(self) -> np.ndarray:
    """Restituisce maschera booleana delle azioni valide per lo step corrente."""
    mask = np.zeros(11, dtype=bool)

    if self._current_step_type == "city":
        # Step città: solo costruzione e idle validi
        mask[0:7] = True  # Monument, Granary, Library, Barracks, Settler, Warrior, idle

    elif self._current_step_type == "warrior":
        # Step warrior: solo skip e movimento validi
        mask[6] = True    # skip (non muovere questo warrior)
        mask[7:11] = True # N/S/E/W

    return mask
```

`self._current_step_type` gestito dalla rotation logic in `step()`.

---

## Aggiornamento: `src/envs/unciv_env.py`

### Stato interno aggiuntivo

```python
def __init__(self, ...) -> None:
    ...
    # Fase 2.1
    self._current_step_type: str = "city"   # "city" | "warrior"
    self._pending_warriors: list = []        # warrior con MP > 0 ancora da decidere
    self._selected_warrior_idx: int = 0

    self.observation_space = gym.spaces.Box(
        low=0.0, high=1.0, shape=(10,), dtype=np.float32
    )
    self.action_space = gym.spaces.Discrete(11)
```

### Logica rotation in `step()`

```python
def step(self, action: int) -> tuple:
    if self._current_step_type == "city":
        self._apply_construction(action)
        # Carica lista warrior con MP > 0
        self._pending_warriors = self._get_warriors_with_movement()
        if self._pending_warriors:
            self._current_step_type = "warrior"
            self._selected_warrior_idx = 0
            # NON avanzare turno — restituire obs aggiornata
            obs = self._get_obs()
            return obs, 0.0, False, False, {}
        else:
            # Nessun warrior → avanza turno direttamente
            return self._advance_and_observe(action)

    elif self._current_step_type == "warrior":
        self._apply_warrior_action(action, self._pending_warriors[self._selected_warrior_idx])
        self._selected_warrior_idx += 1
        if self._selected_warrior_idx < len(self._pending_warriors):
            # Altri warrior da decidere
            obs = self._get_obs()
            return obs, 0.0, False, False, {}
        else:
            # Tutti i warrior hanno deciso → avanza turno
            self._current_step_type = "city"
            return self._advance_and_observe(action)
```

### Nuovo `_apply_warrior_action`

```python
def _apply_warrior_action(self, action: int, warrior: dict) -> None:
    """Muove warrior nella direzione scelta (7=N, 8=S, 9=E, 10=W). 6=skip."""
    if action == 6:
        return  # warrior skip

    direction_map = {
        7: (0, 1),   # Nord: y+1
        8: (0, -1),  # Sud: y-1
        9: (1, 0),   # Est: x+1
        10: (-1, 0), # Ovest: x-1
    }
    dx, dy = direction_map[action]

    with open(self.save_path, 'r') as f:
        raw = json.load(f)

    # Aggiorna posizione warrior nel JSON
    # Logica dipende da formato Unciv headless (Fase 2.0 prerequisita)
    # In Fase 2.0 stub: aggiorna campo posizione nel dict warrior
    for tile in raw.get("tileMap", {}).get("tileList", []):
        unit = tile.get("militaryUnit")
        if unit and unit.get("name") == "Warrior" and unit.get("owner") == "India":
            pos = tile.get("position", {})
            if pos.get("x") == warrior["x"] and pos.get("y") == warrior["y"]:
                new_x = max(0, min(self._map_w - 1, pos["x"] + dx))
                new_y = max(0, min(self._map_h - 1, pos["y"] + dy))
                pos["x"] = new_x
                pos["y"] = new_y
                unit["currentMovement"] = 0  # usato MP
                break

    with open(self.save_path, 'w') as f:
        json.dump(raw, f)
```

---

## Aggiornamento: `src/parsers/state_parser.py`

### Nuovo dataclass `UnitState`

```python
@dataclass
class UnitState:
    """Stato di una singola unità."""
    name: str
    x: int
    y: int
    movement_points: float
    health: int
```

### Campo `units` in `GameState`

```python
@dataclass
class GameState:
    # ... campi Fase 1 invariati ...
    turn: int
    current_player: str
    gold: float
    happiness: float
    cities: list[CityState]
    techs_researched: list[str]
    current_tech: Optional[str]
    map_width: int
    map_height: int

    # Nuovi Fase 2.1
    units: list[UnitState] = field(default_factory=list)
    tiles_explored: int = 0
```

### Nuovo `to_observation_vector` — shape `(10,)`

```python
def to_observation_vector(self, state: GameState, selected_warrior: Optional[UnitState] = None) -> np.ndarray:
    obs = [
        state.turn / 500.0,
        state.gold / 1000.0,
        state.happiness / 20.0,
        len(state.techs_researched) / 80.0,
    ]

    if state.cities:
        c = state.cities[0]
        obs += [c.population / 20.0, len(c.built_buildings) / 20.0]
    else:
        obs += [0.0, 0.0]

    warriors = [u for u in state.units if u.name == "Warrior"]
    obs.append(len(warriors) / 10.0)

    if selected_warrior is not None:
        obs.append(selected_warrior.x / max(state.map_width, 1))
        obs.append(selected_warrior.y / max(state.map_height, 1))
    else:
        obs += [0.0, 0.0]

    obs.append(state.tiles_explored / max(state.map_width * state.map_height, 1))

    return np.array(obs, dtype=np.float32)
```

---

## Aggiornamento: `src/utils/reward.py`

### Nuova componente: exploration reward

```python
REWARD_WEIGHTS = {
    # Fase 1 — invariati
    "population_growth": 2.0,
    "building_complete": 1.5,
    "tech_researched":   3.0,
    "gold_accumulation": 0.5,
    "happiness_penalty": 0.1,
    "idle_penalty":      0.05,

    # Fase 2.1 — nuovi
    "exploration":       0.3,  # per tile nuova esplorata
}


def compute_reward(prev: GameState, curr: GameState, action: int) -> float:
    ...
    # Fase 2.1: esplorazione
    new_tiles = curr.tiles_explored - prev.tiles_explored
    if new_tiles > 0:
        reward += new_tiles * REWARD_WEIGHTS["exploration"]
    ...
```

**Calibrazione:** exploration reward `0.3/tile`. Mappa tiny ~200 tile → max `+60`.
Warrior costa ~13 turni produzione. Con Monument delay: costo opportunità ~3 reward.
Basta esplorare 10 tile nuove per ammortizzare costo Warrior.

---

## Dipendenza: `sb3-contrib`

Aggiungere a `requirements.txt`:
```
sb3-contrib>=2.0.0
```

Installare:
```powershell
pip install sb3-contrib
```

---

## Test: `tests/test_unit_movement.py`

```python
def test_warrior_builds_and_exists():
    """Dopo azione 5 (Warrior) e avanzamento turno, unità appare nello stato."""
    ...

def test_action_mask_city_step():
    """Durante step città, azioni 7-10 mascherate."""
    mask = env.action_masks()
    assert all(mask[0:7])
    assert not any(mask[7:11])

def test_action_mask_warrior_step():
    """Durante step warrior, azioni 0-5 mascherate."""
    # setup: warrior exists with MP > 0
    mask = env.action_masks()
    assert not any(mask[0:6])
    assert mask[6]   # skip valido
    assert all(mask[7:11])

def test_warrior_moves_north():
    """Azione 7 (Nord) incrementa y warrior di 1."""
    ...

def test_exploration_reward():
    """Reward positiva quando tiles_explored aumenta."""
    prev = make_state(tiles_explored=10)
    curr = make_state(tiles_explored=15)
    reward = compute_reward(prev, curr, action=7)
    assert reward == pytest.approx(1.5)  # 5 tile * 0.3

def test_obs_shape():
    obs, _ = env.reset()
    assert obs.shape == (10,)
    assert obs.dtype == np.float32

def test_no_warrior_obs_zeros():
    """Senza warrior: [7],[8] == 0.0, [6] == 0.0."""
    obs, _ = env.reset()
    assert obs[6] == 0.0
    assert obs[7] == 0.0
    assert obs[8] == 0.0
```

---

## Criterio di successo Fase 2.1

```
ep_rew_mean > 5.0
Agente costruisce >= 1 Warrior entro turno 50
Esplora > 30% mappa entro fine episodio (200 turni)
Sopravvive 200 turni con happiness >= 0
```

Monitorare su TensorBoard:
- `unciv/action_Warrior` — deve essere > 5% (agente costruisce warrior)
- `unciv/action_MOVE_*` — deve essere > 10% totale (agente muove)
- `unciv/tiles_explored_mean` — deve crescere nel tempo

---

## Note per Claude Code

- `MaskablePPO` da `sb3-contrib` — non `PPO` standard. Import: `from sb3_contrib import MaskablePPO`
- `action_masks()` chiamato automaticamente da `MaskablePPO` a ogni step — non manualmente
- Settler (action 4) esiste nell'ACTION_MAP ma non ha logica di fondazione città in Fase 2.1.
  Se agente sceglie Settler, costruisce normalmente ma unità non ha logica movement speciale.
  Fondazione città implementata in Fase 2.2.
- `_current_step_type` resettato a `"city"` a ogni `reset()`
- Map boundary check in `_apply_warrior_action`: warrior non può uscire dalla mappa
- Tiles esplorate: in Unciv headless tracciate automaticamente nel save file.
  In stub Python: incrementare di 1 per ogni movimento (approssimazione).
