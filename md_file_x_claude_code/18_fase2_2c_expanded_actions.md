# File 18 — Fase 2.2c: Expanded Action Space + Obs

## Obiettivo
Espandere ACTION_MAP da 5 costruzioni hardcoded a ~14 costruzioni lette dal ruleset.
Aggiornare observation vector di conseguenza. Aggiornare tutti i contratti.

**Prerequisiti:** File 16 + 17 completati e testati.

---

## Nuovo ACTION_MAP

Generato a runtime in `unciv_env.py.__init__` da `load_early_game_constructions()`.
Ordine fisso: edifici (alfabetico) → unità (alfabetico) → skip → MOVE_*.

```
Edifici (9):  Barracks, Colosseum, Courthouse, Granary, Library,
              Monument, Stable, Temple, Walls
Unità   (5):  Scout, Settler, Spearman, Warrior, Worker
Skip    (1):  None
Mosse   (4):  MOVE_NORTH, MOVE_SOUTH, MOVE_EAST, MOVE_WEST
─────────────────────────────────────────────────────────
Totale: 19 → Discrete(19)
```

> Il numero esatto dipende dall'output di `load_early_game_constructions()` —
> calcolarlo in `__init__` dinamicamente, non hardcoded.

---

## Costruzione ACTION_MAP in `__init__`

```python
constructions = load_early_game_constructions(jar_path)
buildings = sorted([c.name for c in constructions if not c.is_unit])
units     = sorted([c.name for c in constructions if c.is_unit])

action_list = buildings + units + [None] + ["MOVE_NORTH", "MOVE_SOUTH", "MOVE_EAST", "MOVE_WEST"]
self.ACTION_MAP = {i: name for i, name in enumerate(action_list)}

self._skip_idx = action_list.index(None)
self._move_start_idx = self._skip_idx + 1
self._n_construction_actions = len(buildings) + len(units)

self.action_space = gym.spaces.Discrete(len(self.ACTION_MAP))
```

---

## Nuovo Observation Vector

Espansione della sezione edifici da 3 flag → 9 flag (+6 slot).

**Layout nuovo (58,):**

| Range | Slot | Contenuto |
|---|---|---|
| [0-5] | 6 | Globale: turn, gold, happiness, sci/t, cult/t, n_cities |
| [6-24] | 19 | Città 1: pop, food_prog, prod_prog, gold/t, food/t, prod/t, n_buildings, **9 flag edifici**, tiles_worked, x, y |
| [25-32] | 8 | Tech: n_techs, tech_progress, 6 flag tech chiave |
| [33-40] | 8 | Unità: n_warriors, n_settlers, n_other, warrior_xy, settler_xy, tiles_explored |
| [41-50] | 10 | Città 2 (zeros se assente) — stessa struttura città 1 ridotta |
| [51-52] | 2 | Diplomazia: n_known_civs, at_war |
| [53-56] | 4 | Unità selezionata: sel_x, sel_y, sel_movement, tiles_explored_ratio |

**→ shape (57,)** (calcolare esatto durante implementazione, aggiornare assert)

**9 flag edifici in ordine alfabetico** (stesso ordine ACTION_MAP edifici):
```
has_barracks, has_colosseum, has_courthouse, has_granary, has_library,
has_monument, has_stable, has_temple, has_walls
```

---

## Modifiche a `state_parser.py`

### `to_observation_vector()` — sezione città 1

Sostituire:
```python
# vecchio: 3 flag
has_monument = 1.0 if "Monument" in city.built_buildings else 0.0
has_library  = 1.0 if "Library"  in city.built_buildings else 0.0
has_market   = 1.0 if "Market"   in city.built_buildings else 0.0
```

Con:
```python
# nuovo: 9 flag — ordine alfabetico fisso
TRACKED_BUILDINGS = ["Barracks", "Colosseum", "Courthouse", "Granary", "Library",
                     "Monument", "Stable", "Temple", "Walls"]
building_flags = [1.0 if b in city.built_buildings else 0.0 for b in TRACKED_BUILDINGS]
```

### Assert finale
```python
assert result.shape == (57,)   # aggiornare da (52,)
```

---

## Aggiornamento `_apply_action()`

```python
def _apply_action(self, action: int) -> None:
    name = self.ACTION_MAP.get(action)
    if name is None or name.startswith("MOVE_"):
        return
    # scrive name in currentConstruction del JSON
    # (logica identica all'attuale, ma name viene dal nuovo ACTION_MAP)
```

---

## Contratti da aggiornare

### `CLAUDE.md`

| Contratto | Vecchio | Nuovo |
|---|---|---|
| Dimensione obs | `(52,)` | `(57,)` *(o valore esatto)* |
| Numero azioni | `11` | `19` *(o valore esatto)* |

### `ARCHITECTURE.md`
- Sezione "Spazi Gymnasium": aggiornare shape e ACTION_MAP
- Sezione obs layout: aggiornare tabella

### `config/default_config.yaml`
- Nessuna modifica necessaria

---

## File da modificare

- `src/envs/unciv_env.py` (ACTION_MAP dinamico, action_space, `_apply_action`, `action_masks` skip/move idx)
- `src/parsers/state_parser.py` (`to_observation_vector`: 9 flag, assert shape)
- `CLAUDE.md` (contratti obs shape + n azioni)
- `ARCHITECTURE.md` (ACTION_MAP, obs layout, Discrete(N))
- `tests/test_env.py` (n azioni, mask shape)
- `tests/test_parser.py` (obs shape assert)

---

## Test richiesti

```python
test_action_space_size()
    # action_space.n == len(ACTION_MAP) (19 circa)

test_obs_shape_updated()
    # obs.shape == (57,)  ← valore esatto da determinare

test_monument_in_action_map()
    # "Monument" in ACTION_MAP.values()

test_warrior_in_action_map()
    # "Warrior" in ACTION_MAP.values()

test_skip_in_action_map()
    # None in ACTION_MAP.values()

test_move_north_in_action_map()
    # "MOVE_NORTH" in ACTION_MAP.values()

test_building_flags_all_zero_fresh_game()
    # nuova partita: tutti 9 flag edifici = 0

test_building_flags_monument_set()
    # dopo costruzione Monument: has_monument = 1.0
```

---

## Note implementative

- Calcolare shape obs esatta leggendo `to_observation_vector()` dopo le modifiche
- Aggiornare l'assert in `to_observation_vector()` con il valore esatto
- I vecchi checkpoint `unciv_mppo_*` sono incompatibili con il nuovo obs shape — documentarlo in WORK_LOG
- Training ripartirà da zero dopo questo step
