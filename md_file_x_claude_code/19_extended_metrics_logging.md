# File 19 — Extended Metrics Logging

## Obiettivo

Aggiungere un sistema di monitoring esteso per preparare le prossime fasi di sviluppo
e supportare la futura definizione delle reward function.

Le metriche sono raccolte in tre livelli:
1. **Parsing** — nuovi campi in `GameState` letti dal JSON Unciv
2. **Tracking** — contatori per-episodio in `UncivEnv` (delta tra turni)
3. **Logging** — `logger.record()` in `UncivMetricsCallback`

**Prerequisiti:** File 18 completato e testato (obs `(57,)`, action space `Discrete(19)`).

---

## Metriche da loggare

### Gruppo A — Già in `GameState`, da estendere

| Metrica | Fonte JSON | Campo GameState attuale |
|---|---|---|
| Tecnologie ricercate (lista) | `tech.techsResearched` | `techs_researched` (già presente) |
| Oro totale episodio | delta `gold` tra turni | nuovo contatore env |
| Oro medio per turno | totale / n_turns | calcolato in callback |

### Gruppo B — Nuovi campi `GameState`

| Metrica | Fonte JSON Unciv | Campo da aggiungere |
|---|---|---|
| Tiles esplorate | `civ.exploredTiles` (list of `{x,y}`) | `tiles_explored: int` |
| Territorio città (tiles totali) | `city.tiles` (list of `{x,y}`) per ogni città | `city_territory_tiles: int` |
| Scienza per turno | `tech.scienceOfLast8Turns[-1]` | `science_per_turn: float` |
| Cultura per turno | `policies.storedCulture` delta OR `statsHistory` | `culture_per_turn: float` |
| Risorse strategiche | `civ.detailedCivResources` dove `resource.resourceType == "Strategic"` | `strategic_resources: dict[str, int]` |
| Risorse rare (luxury) | `civ.detailedCivResources` dove `resource.resourceType == "Luxury"` | `luxury_resources: dict[str, int]` |

### Gruppo C — Tracking delta per-episodio in `UncivEnv`

Questi NON vengono salvati in `GameState` — rilevati confrontando stato corrente vs precedente.

| Metrica | Come rilevare |
|---|---|
| Unità create per tipo | `curr_units` - `prev_units` per nome |
| Costruzioni completate (conteggio) | `curr.built_buildings` - `prev.built_buildings` per ogni città |
| Tipologia costruzioni completate | stessa logica — lista nomi nuovi edifici |
| Scienza totale episodio | somma `science_per_turn` su tutti i turni |
| Cultura totale episodio | somma `culture_per_turn` su tutti i turni |
| Oro totale episodio | somma delta `gold` su tutti i turni |

---

## Modifiche a `state_parser.py`

### `GameState` dataclass — nuovi campi

```python
@dataclass
class GameState:
    # ... campi esistenti ...
    tiles_explored: int = 0
    city_territory_tiles: int = 0
    science_per_turn: float = 0.0
    culture_per_turn: float = 0.0
    strategic_resources: dict[str, int] = field(default_factory=dict)
    luxury_resources: dict[str, int] = field(default_factory=dict)
```

### `_extract_game_state()` — parsing nuovi campi

```python
# Tiles esplorate
explored = civ.get('exploredTiles', [])
tiles_explored = len(explored)

# Territorio città
city_territory_tiles = sum(len(c.get('tiles', [])) for c in civ.get('cities', []))

# Scienza per turno
science_history = civ.get('tech', {}).get('scienceOfLast8Turns') or []
science_per_turn = float(science_history[-1]) if science_history else 0.0

# Cultura per turno — da statsHistory (chiave 'C')
culture_per_turn = _parse_culture_per_turn(civ)  # helper privato

# Risorse
strategic_resources: dict[str, int] = {}
luxury_resources: dict[str, int] = {}
for entry in civ.get('detailedCivResources', []):
    res = entry.get('resource', {})
    name = res.get('name', '')
    amount = int(entry.get('amount', 0))
    rtype = res.get('resourceType', '')
    if rtype == 'Strategic':
        strategic_resources[name] = strategic_resources.get(name, 0) + amount
    elif rtype == 'Luxury':
        luxury_resources[name] = luxury_resources.get(name, 0) + amount
```

### Helper `_parse_culture_per_turn()`

`statsHistory` in Unciv codifica culture come chiave `C`. Usare la stessa logica
già applicata per science/happiness in `_parse_stats_history()`. Se non disponibile,
fallback a `0.0`.

---

## Modifiche a `unciv_env.py`

### Nuovi attributi episodio in `__init__` e `reset()`

```python
# reset() e __init__
self._ep_total_gold: float = 0.0
self._ep_total_science: float = 0.0
self._ep_total_culture: float = 0.0
self._ep_buildings_built: dict[str, int] = {}
self._ep_units_built: dict[str, int] = {}
```

### Aggiornamento in `_advance_game_turn()`

Dopo aver calcolato `prev_state` e `curr_state`:

```python
# Accumula risorse
if self._prev_state:
    gold_delta = max(0.0, curr.gold - prev.gold)
    self._ep_total_gold += gold_delta
self._ep_total_science += curr.science_per_turn
self._ep_total_culture += curr.culture_per_turn

# Nuove costruzioni (delta edifici città per città)
if self._prev_state:
    prev_built = {b for c in prev.cities for b in c.built_buildings}
    curr_built = {b for c in curr.cities for b in c.built_buildings}
    for b in curr_built - prev_built:
        self._ep_buildings_built[b] = self._ep_buildings_built.get(b, 0) + 1

# Nuove unità (confronto nomi)
if self._prev_state:
    prev_unit_counts = _count_by_name(prev.units)
    curr_unit_counts = _count_by_name(curr.units)
    for name, cnt in curr_unit_counts.items():
        delta = max(0, cnt - prev_unit_counts.get(name, 0))
        if delta:
            self._ep_units_built[name] = self._ep_units_built.get(name, 0) + delta
```

### Aggiornamento `info` dict in `_advance_game_turn()`

```python
info = {
    # metriche esistenti
    "turn": ..., "gold": ..., "happiness": ..., "n_cities": ...,
    "n_techs": ..., "population": ...,
    # nuove metriche
    "tiles_explored": curr.tiles_explored,
    "city_territory_tiles": curr.city_territory_tiles,
    "science_per_turn": curr.science_per_turn,
    "culture_per_turn": curr.culture_per_turn,
    "strategic_resources": curr.strategic_resources,
    "luxury_resources": curr.luxury_resources,
    "ep_total_gold": self._ep_total_gold,
    "ep_total_science": self._ep_total_science,
    "ep_total_culture": self._ep_total_culture,
    "ep_buildings_built": dict(self._ep_buildings_built),
    "ep_units_built": dict(self._ep_units_built),
}
```

---

## Modifiche a `callbacks.py`

### `UncivMetricsCallback._on_rollout_end()` — nuovi `logger.record()`

```python
# Metriche per turno (media episodi)
self.logger.record("unciv/tiles_explored_mean",        np.mean([i.get("tiles_explored", 0) for i in infos]))
self.logger.record("unciv/city_territory_mean",        np.mean([i.get("city_territory_tiles", 0) for i in infos]))
self.logger.record("unciv/science_per_turn_mean",      np.mean([i.get("science_per_turn", 0) for i in infos]))
self.logger.record("unciv/culture_per_turn_mean",      np.mean([i.get("culture_per_turn", 0) for i in infos]))

# Metriche totale episodio
self.logger.record("unciv/ep_total_gold_mean",         np.mean([i.get("ep_total_gold", 0) for i in infos]))
self.logger.record("unciv/ep_total_science_mean",      np.mean([i.get("ep_total_science", 0) for i in infos]))
self.logger.record("unciv/ep_total_culture_mean",      np.mean([i.get("ep_total_culture", 0) for i in infos]))

# Costruzioni completate per tipo (top buildings)
for b in ["Monument", "Granary", "Library", "Barracks", "Temple", "Colosseum", "Walls", "Stable", "Courthouse"]:
    self.logger.record(
        f"unciv/built_{b.lower()}_mean",
        np.mean([i.get("ep_buildings_built", {}).get(b, 0) for i in infos])
    )

# Unità create per tipo
for u in ["Warrior", "Scout", "Settler", "Worker", "Spearman"]:
    self.logger.record(
        f"unciv/trained_{u.lower()}_mean",
        np.mean([i.get("ep_units_built", {}).get(u, 0) for i in infos])
    )

# Risorse (presenti/assenti, media episodi)
# Loggare solo totale strategiche e luxury per semplicità
self.logger.record("unciv/strategic_res_count_mean",
    np.mean([sum(i.get("strategic_resources", {}).values()) for i in infos]))
self.logger.record("unciv/luxury_res_count_mean",
    np.mean([sum(i.get("luxury_resources", {}).values()) for i in infos]))
```

> `infos` = `self._episode_infos` (lista dict `info` da ogni episodio completato nel rollout)

---

## File da modificare

- `src/parsers/state_parser.py` (nuovi campi `GameState`, parsing tiles/risorse/scienza/cultura)
- `src/envs/unciv_env.py` (contatori episodio, `info` dict esteso, `reset()`)
- `src/utils/callbacks.py` (`logger.record` nuove metriche)
- `tests/test_env.py` (nuovi test su `info` dict e contatori episodio)
- `tests/test_parser.py` (nuovi test su campi `GameState`)

---

## Test richiesti

```python
# state_parser.py
test_tiles_explored_empty_civ()
    # exploredTiles assente → tiles_explored == 0

test_tiles_explored_count()
    # exploredTiles con 10 voci → tiles_explored == 10

test_city_territory_tiles()
    # città con 7 tiles → city_territory_tiles == 7

test_strategic_resources_parsed()
    # detailedCivResources con ferro amount=2 → strategic_resources == {"Iron": 2}

test_luxury_resources_parsed()
    # detailedCivResources con seta amount=1 → luxury_resources == {"Silk": 1}

test_science_per_turn_from_history()
    # scienceOfLast8Turns=[5,8,10] → science_per_turn == 10.0

# unciv_env.py
test_ep_buildings_built_tracks_new_construction()
    # turno 1: built=[], turno 2: built=["Monument"] → ep_buildings_built == {"Monument": 1}

test_ep_units_built_tracks_new_unit()
    # turno 1: units=[], turno 2: units=[Warrior] → ep_units_built == {"Warrior": 1}

test_ep_totals_reset_on_episode_reset()
    # dopo reset() → ep_total_gold == 0, ep_buildings_built == {}

test_info_contains_new_metrics()
    # info dict da _advance_game_turn contiene tutte le nuove chiavi
```

---

## Note implementative

- `gold_delta = max(0, curr.gold - prev.gold)`: accumulare solo incrementi (l'oro può scendere per maintenance)
- `detailedCivResources` in Unciv può essere assente o lista vuota su partite nuove — gestire con `or []`
- `culture_per_turn` via `statsHistory` può essere 0 nelle prime versioni — fallback sicuro a 0.0
- I contatori `_ep_buildings_built` / `_ep_units_built` sono dict Python — mai aggiungere a `observation_space`
- Questi dati sono **solo per monitoring** — non entrano nell'obs vector né nella reward (per ora)
- Vecchi checkpoint rimangono compatibili: nessuna modifica a obs shape o action space
