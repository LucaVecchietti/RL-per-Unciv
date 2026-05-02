# 09 — Real Observation Space (Fase 2.0 completa)

## Obiettivo

Usare lo stato reale di Unciv come observation per l'agente.
Dopo il fork (File 08), Unciv processa i turni realmente — ma il parser legge
ancora solo 7 valori approssimati dal save file.

Questa fase porta l'observation da `(7,)` → `(N,)` con dati reali:
tile yields, edifici reali, unità, tech progress, happiness reale.

**Prerequisito:** File 08 completato e training base funzionante.

---

## Perché l'obs attuale non è sufficiente

| Campo attuale | Problema |
|---|---|
| `turn / 500` | OK |
| `gold / 1000` | OK |
| `happiness / 20` | Approssimato (simulatore) — ora reale |
| `n_cities / 10` | Limitato: non dice nulla su qualità città |
| `n_techs / 80` | Non dice quale tech, né progress % |
| `pop / 20` | Solo città 0, no tile yields che guidano crescita |
| `n_buildings / 20` | Non specifica quali edifici (Monument vs Library è diverso) |

Per un agente competitivo, deve sapere:
- Qual è il yield food/production/gold della città → decide cosa costruire
- Quale tech sta ricercando e quanti turni mancano → decide idle vs push
- Dove sono le sue unità → decide movimento
- Happiness breakdown → capisce perché è infelice

---

## Nuovo observation vector — Fase 2.0 completa

Shape: `(48,)` float32. Tutto da save file Unciv reale.

```
# GLOBALE (6 valori)
[0]  turn / 500
[1]  gold / 1000
[2]  happiness / 20                        ← da Unciv reale
[3]  science_per_turn / 50                 ← da Unciv reale (era assente)
[4]  culture_per_turn / 20                 ← da Unciv reale (era assente)
[5]  n_cities / 10

# PRIMA CITTÀ (16 valori)
[6]  population / 20
[7]  food_stored / food_threshold          ← progress crescita pop (0→1)
[8]  production_stored / current_cost      ← progress costruzione (0→1)
[9]  gold_per_turn_city / 20
[10] food_per_turn / 20                    ← yield cibo tiles lavorate
[11] production_per_turn / 20              ← yield prod tiles lavorate
[12] n_buildings / 20
[13] has_monument (0/1)
[14] has_granary (0/1)
[15] has_library (0/1)
[16] has_barracks (0/1)
[17] has_walls (0/1)
[18] has_market (0/1)
[19] city_strength / 30                    ← difesa città
[20] tiles_worked / 36                     ← quante tile lavorate
[21] city_x / map_width
[22] city_y / map_height   (NOTA: mappa potrebbe non essere letta — usare 0 se assente)

# TECH (8 valori)
[22] n_techs_researched / 80
[23] current_tech_progress / current_tech_cost  ← % completamento tech corrente
[24] has_agriculture (0/1)
[25] has_pottery (0/1)
[26] has_writing (0/1)
[27] has_mining (0/1)
[28] has_bronze_working (0/1)
[29] has_animal_husbandry (0/1)

# UNITÀ (8 valori)
[30] n_warriors / 10
[31] n_settlers / 5
[32] n_other_units / 10
[33] nearest_warrior_x / map_width   (0 se nessun warrior)
[34] nearest_warrior_y / map_height
[35] nearest_settler_x / map_width   (0 se nessun settler)
[36] nearest_settler_y / map_height
[37] tiles_explored / total_tiles

# SECONDA CITTÀ (8 valori — zeros se non esiste)
[38] city2_population / 20
[39] city2_food_per_turn / 20
[40] city2_production_per_turn / 20
[41] city2_n_buildings / 20
[42] city2_food_progress / food_threshold
[43] city2_production_progress / cost
[44] city2_x / map_width
[45] city2_y / map_height

# DIPLOMAZIA (2 valori)
[46] n_known_civs / 10
[47] at_war (0/1)
```

> **Contratto:** shape `(48,)` float32, valori in `[0, ~1]`.
> Aggiornare tabella in `CLAUDE.md`.

---

## Aggiornamento: `src/parsers/state_parser.py`

### Nuovi dataclass

```python
@dataclass
class UnitState:
    name: str
    x: int
    y: int
    movement_points: float
    health: int

@dataclass
class CityState:
    name: str
    population: int
    current_construction: str
    built_buildings: list[str]
    health: int
    tiles_count: int
    # Nuovi Fase 2.0
    food_stored: float = 0.0
    food_threshold: float = 10.0
    food_per_turn: float = 2.0
    production_stored: float = 0.0
    current_construction_cost: float = 60.0
    production_per_turn: float = 3.0
    gold_per_turn: float = 1.0
    tiles_worked: int = 1
    x: int = 0
    y: int = 0

@dataclass
class GameState:
    turn: int
    current_player: str
    gold: float
    happiness: float
    cities: list[CityState]
    techs_researched: list[str]
    current_tech: Optional[str]
    map_width: int
    map_height: int
    # Nuovi Fase 2.0
    units: list[UnitState] = field(default_factory=list)
    tiles_explored: int = 0
    science_per_turn: float = 2.0
    culture_per_turn: float = 0.0
    current_tech_progress: float = 0.0
    current_tech_cost: float = 20.0
    n_known_civs: int = 0
    at_war: bool = False
    gold_per_turn: float = 1.0
```

### Parsing da save file Unciv reale

Unciv salva in JSON (gzip o plain). I campi rilevanti nel JSON:

```python
def _extract_game_state(self, raw: dict) -> GameState:
    civ = self._find_player_civ(raw)

    # Scienza/turno — campo "statsForNextTurn" o calcolato da civInfo
    stats = civ.get("statsForNextTurn", {})
    science_per_turn = stats.get("science", 2.0)
    culture_per_turn = stats.get("culture", 0.0)
    gold_per_turn = stats.get("gold", 1.0)

    # Tech in corso
    tech_manager = civ.get("tech", {})
    current_tech = tech_manager.get("currentTechName")
    current_tech_progress = tech_manager.get("overflowScience", 0.0)
    # oppure: tech_manager.get("researchedTechsWithEras", {}) per lista completa

    # Unità — nelle tile della mappa
    units = self._parse_units(raw, civ.get("civName", "India"))

    # Diplomazia
    diplomacy = civ.get("diplomacy", {})
    n_known_civs = len(diplomacy)
    at_war = any(d.get("diplomaticStatus") == "War" for d in diplomacy.values())

    cities = [self._parse_city(c) for c in civ.get("cities", [])]

    return GameState(
        turn=raw.get("turns", 0),
        current_player=civ.get("civName", "India"),
        gold=civ.get("gold", 0.0),
        happiness=civ.get("happinessForNextTurn", 0.0),
        cities=cities,
        techs_researched=list(tech_manager.get("techsResearched", {}).keys()),
        current_tech=current_tech,
        map_width=raw.get("tileMap", {}).get("mapParameters", {}).get("mapSize", {}).get("width", 20),
        map_height=raw.get("tileMap", {}).get("mapParameters", {}).get("mapSize", {}).get("height", 20),
        units=units,
        science_per_turn=science_per_turn,
        culture_per_turn=culture_per_turn,
        current_tech_progress=current_tech_progress,
        n_known_civs=n_known_civs,
        at_war=at_war,
        gold_per_turn=gold_per_turn,
    )


def _parse_city(self, city: dict) -> CityState:
    constructions = city.get("cityConstructions", {})
    built = list(constructions.get("builtBuildings", []))
    current = constructions.get("currentConstruction", "")
    stored_prod = constructions.get("productionOverflow", 0.0)

    stats = city.get("cityStats", {}).get("currentCityStats", {})
    food_per_turn = stats.get("food", 2.0)
    prod_per_turn = stats.get("production", 3.0)
    gold_per_turn = stats.get("gold", 1.0)

    pop_data = city.get("population", {})
    population = pop_data.get("population", 1)
    food_stored = pop_data.get("foodStored", 0.0)
    food_threshold = 10 + population * 3  # fallback se non in JSON

    pos = city.get("location", {})

    return CityState(
        name=city.get("name", ""),
        population=population,
        current_construction=current,
        built_buildings=built,
        health=city.get("health", 200),
        tiles_count=len(city.get("tiles", [])),
        food_stored=food_stored,
        food_threshold=food_threshold,
        food_per_turn=food_per_turn,
        production_stored=stored_prod,
        production_per_turn=prod_per_turn,
        gold_per_turn=gold_per_turn,
        tiles_worked=len(city.get("workedTiles", [])),
        x=pos.get("x", 0),
        y=pos.get("y", 0),
    )


def _parse_units(self, raw: dict, player_civ: str) -> list[UnitState]:
    units = []
    for tile in raw.get("tileMap", {}).get("tileList", []):
        for key in ["militaryUnit", "civilianUnit"]:
            unit = tile.get(key)
            if unit and unit.get("owner") == player_civ:
                pos = tile.get("position", {})
                units.append(UnitState(
                    name=unit.get("name", ""),
                    x=int(pos.get("x", 0)),
                    y=int(pos.get("y", 0)),
                    movement_points=unit.get("currentMovement", 0.0),
                    health=unit.get("health", 100),
                ))
    return units
```

> ⚠️ I path JSON esatti (`cityStats`, `population.foodStored`, ecc.) dipendono
> dalla versione Unciv. **Verificare su un save file reale prima di implementare.**
> Stampare le chiavi del dict con `print(city.keys())` per trovare i campi corretti.

### Nuovo `to_observation_vector` — shape `(48,)`

Vedere spec sopra. Implementare con `np.clip` per valori fuori range.

---

## Aggiornamento: `src/envs/unciv_env.py`

```python
self.observation_space = gym.spaces.Box(
    low=0.0, high=1.0, shape=(48,), dtype=np.float32
)
```

Tutto il resto invariato — `_advance_turn` già delega a headless.

---

## Ordine implementazione

```
Step 1 → Stampa chiavi JSON di un save file reale per trovare i path corretti
           python -c "
           import json
           with open('saves/current_game_0.json') as f:
               raw = json.load(f)
           civ = [c for c in raw['civilizations'] if c['civName']=='India'][0]
           print('CIV KEYS:', list(civ.keys()))
           print('CITY KEYS:', list(civ['cities'][0].keys()))
           print('CONSTRUCTIONS:', list(civ['cities'][0]['cityConstructions'].keys()))
           "

Step 2 → Aggiornare GameState e CityState con nuovi campi
Step 3 → Aggiornare _parse_city() e _extract_game_state()
Step 4 → Aggiornare _parse_units()
Step 5 → Implementare nuovo to_observation_vector() shape (48,)
Step 6 → pytest tests/test_parser.py -v  ← deve passare
Step 7 → Aggiornare test_parser.py (shape 7→48)
Step 8 → Aggiornare unciv_env.py (observation_space (48,))
Step 9 → Aggiornare test_env.py (shape, contratti)
Step 10 → pytest tests/ -v              ← tutti devono passare
Step 11 → Aggiornare CLAUDE.md (contratti: (48,))
Step 12 → git commit
```

---

## Criterio di successo

- `python -m pytest tests/ -v` → tutti verdi
- `ep_rew_mean` con Unciv reale comparable a Fase 1.5 (≥ 30)
- Observation contiene dati reali verificabili (es. `obs[7]` = food progress, non zero fisso)

---

## Note per Claude Code

- **Step 1 è obbligatorio** — i path JSON variano tra versioni Unciv. Non indovinare.
- `statsForNextTurn` potrebbe non esistere nei save vecchi — usare fallback `0.0`
- `cityStats.currentCityStats` potrebbe essere calcolato a runtime, non salvato.
  In quel caso, sommare manualmente tile yields da `workedTiles`.
- Se un campo non esiste nel JSON, usare il valore del simulatore Python come fallback
  (non crashare — degradare silenziosamente).
- `map_width/height` potrebbero non essere nel tileMap per mappe tiny — fallback a 20.
- Aggiornare la tabella contratti in `CLAUDE.md` prima di modificare state_parser.py.
