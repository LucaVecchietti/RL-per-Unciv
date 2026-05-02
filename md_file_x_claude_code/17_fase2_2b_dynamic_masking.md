# File 17 — Fase 2.2b: Dynamic Action Masking

## Obiettivo
Aggiornare `action_masks()` in `unciv_env.py` per mascherare le costruzioni non disponibili
basandosi sullo stato corrente (tech ricercate, edifici già costruiti).

**Prerequisito:** File 16 completato (`ruleset_reader.py` disponibile e testato).

Action space e obs vector NON cambiano in questo step — solo la logica del masking.

---

## Problema attuale

`action_masks()` city step ritorna `[True]*7 + [False]*4` — tutte le costruzioni sempre disponibili.

Conseguenza: l'agente prova a costruire Library senza Writing → Unciv ignora o resetta →
nessun reward → apprendimento sprecato.

---

## Logica masking city step (nuova)

```
Per ogni azione i in [0, N_CONSTRUCTION_ACTIONS):
    name = ACTION_MAP[i]

    se name è None (skip):
        mask[i] = True  # skip sempre disponibile

    altrimenti:
        req = PREREQ_MAP.get(name)          # da ruleset_reader
        tech_ok = (req is None) or (req in state.techs_researched)

        se is_building(name):
            already_built = name in city.built_buildings
            mask[i] = tech_ok and not already_built

        se is_unit(name):
            mask[i] = tech_ok

# Unit step invariato: skip + MOVE_*
```

**Invariante:** almeno 1 azione sempre True in city step (skip garantisce questo).

---

## Modifiche a `unciv_env.py`

### `__init__` — aggiungere dopo init headless

```python
from src.utils.ruleset_reader import load_early_game_constructions

constructions = load_early_game_constructions(jar_path)
self._prereq_map: dict[str, Optional[str]] = {
    c.name: c.required_tech for c in constructions
}
self._unit_names: set[str] = {c.name for c in constructions if c.is_unit}
self._building_names: set[str] = {c.name for c in constructions if not c.is_unit}
```

### `action_masks()` — sostituire logica city step

```python
def action_masks(self) -> np.ndarray:
    mask = np.zeros(len(ACTION_MAP), dtype=bool)
    if self._step_type == "city":
        state = self._current_state
        city = state.cities[0] if state.cities else None
        built = set(city.built_buildings) if city else set()
        for i, name in ACTION_MAP.items():
            if name is None:                          # skip
                mask[i] = True
            elif name.startswith("MOVE_"):            # movimento — non in city step
                mask[i] = False
            else:
                req = self._prereq_map.get(name)
                tech_ok = req is None or req in state.techs_researched
                if name in self._building_names:
                    mask[i] = tech_ok and name not in built
                else:
                    mask[i] = tech_ok
    elif self._step_type == "unit":
        skip_idx = next(i for i, n in ACTION_MAP.items() if n is None)
        mask[skip_idx] = True
        for i, name in ACTION_MAP.items():
            if isinstance(name, str) and name.startswith("MOVE_"):
                mask[i] = True
    return mask
```

---

## Modifiche a `CityState` (verifica)

`CityState.built_buildings: list[str]` esiste già in `state_parser.py`.
Verificare che il parser popoli correttamente questo campo dal JSON Unciv
(chiave `cityConstructions.builtBuildings`).

Se assente o vuoto → aggiungere parsing in `_parse_city()`.

---

## File da modificare

- `src/envs/unciv_env.py` (`__init__`, `action_masks`)
- `src/parsers/state_parser.py` (verifica/fix `built_buildings` parsing)
- `tests/test_env.py` (aggiornare test masking)

---

## Test richiesti

```python
test_mask_monument_available_when_not_built()
    # Monument no req, non costruito → True

test_mask_monument_blocked_when_already_built()
    # Monument in built_buildings → False

test_mask_library_blocked_without_writing()
    # Library req Writing, techs=[] → False

test_mask_library_available_with_writing()
    # Library req Writing, techs=["Writing"] → True

test_mask_skip_always_true_city_step()
    # skip action sempre True indipendentemente dallo stato

test_mask_move_false_in_city_step()
    # MOVE_* sempre False in city step

test_at_least_one_true_city_step()
    # garantisce skip=True → mai deadlock

test_unit_step_mask_unchanged()
    # unit step: skip + MOVE_* True, tutto il resto False
```

---

## Note implementative

- `_prereq_map` caricato una volta in `__init__` — nessun overhead a runtime
- Se `state.cities` è vuota (edge case reset): skip only mask — no crash
- Non modificare il numero di azioni in questo step (Action space resta Discrete(11))
- Questo step NON cambia obs vector né contratti — solo masking più intelligente
