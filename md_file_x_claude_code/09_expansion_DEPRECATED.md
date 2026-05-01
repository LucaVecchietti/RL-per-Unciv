# 09 — Espansione (Fase 2)

## Obiettivo
Estendere l'agente per gestire l'espansione territoriale: fondare nuove città,
esplorare la mappa, gestire più unità. L'observation space cresce da (7,) a (12,).

---

## Cosa cambia rispetto alla Fase 1

| Componente | Fase 1 | Fase 2 |
|---|---|---|
| Observation space | `(7,)` | `(12,)` |
| Azioni | 7 (solo costruzioni) | 9 (+ Settler move, Scout explore) |
| Città gestite | 1 | fino a 3 |
| Mappa | ignorata | tiles esplorate tracciate |
| Modello PPO | da zero | transfer learning da Fase 1 |

---

## Nuovo spazio delle osservazioni — (12,)

```
# Invariati dalla Fase 1
[0]  turn / 500
[1]  gold / 1000
[2]  happiness / 20
[3]  n_cities / 10
[4]  n_techs / 80
[5]  first_city_population / 20
[6]  first_city_built_buildings / 20

# Nuovi in Fase 2
[7]  settler_available     (0.0 o 1.0 — ho un Settler libero?)
[8]  scout_available       (0.0 o 1.0 — ho uno Scout libero?)
[9]  tiles_explored / 200  (percentuale mappa esplorata)
[10] total_population / 50 (popolazione totale tutte le città)
[11] happiness_per_city    (happiness / max(n_cities, 1), normalizzato)
```

> ⚠️ **Contratto critico:** aggiornare la tabella in CLAUDE.md:
> `Dimensione observation vector | (12,) float32 | state_parser.py ↔ unciv_env.py`

---

## Nuovo spazio delle azioni — Discrete(9)

```python
ACTION_MAP = {
    # Fase 1 — invariate
    0: "Monument",
    1: "Granary",
    2: "Library",
    3: "Barracks",
    4: "Settler",       # costruisce Settler (come prima)
    5: "Warrior",
    6: None,            # Fine turno

    # Fase 2 — nuove
    7: "FOUND_CITY",    # Settler fonda una nuova città
    8: "EXPLORE",       # Scout esplora tile adiacente
}
```

---

## Aggiornamento: `src/parsers/state_parser.py`

### Nuovi campi in `GameState`

```python
@dataclass
class UnitState:
    """Stato di una singola unità."""
    name: str
    x: int
    y: int
    movement_points: float
    health: int


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

    # Nuovi Fase 2
    units: list[UnitState] = field(default_factory=list)
    tiles_explored: int = 0
```

### Parsing unità

```python
def _parse_units(self, civ_data: dict) -> list[UnitState]:
    """Estrae le unità della civilizzazione dal save file."""
    units = []
    # Le unità sono nelle tiles della mappa, non nella civ
    # Bisogna scorrere tileMap e cercare le unità della nostra civ
    for tile in self._raw_tiles:
        for unit_key in ["militaryUnit", "civilianUnit"]:
            unit = tile.get(unit_key)
            if unit and unit.get("owner") == self.player_civ:
                pos = tile.get("position", {})
                units.append(UnitState(
                    name=unit.get("name", ""),
                    x=pos.get("x", 0),
                    y=pos.get("y", 0),
                    movement_points=unit.get("currentMovement", 0),
                    health=unit.get("health", 100),
                ))
    return units
```

### Nuovo `to_observation_vector` — shape (12,)

```python
def to_observation_vector(self, state: GameState) -> np.ndarray:
    """
    Fase 2 — vettore di dimensione (12,) float32:
      [0]  turn / 500
      [1]  gold / 1000
      [2]  happiness / 20
      [3]  n_cities / 10
      [4]  n_techs / 80
      [5]  first_city_population / 20
      [6]  first_city_built_buildings / 20
      [7]  settler_available (0.0 / 1.0)
      [8]  scout_available (0.0 / 1.0)
      [9]  tiles_explored / 200
      [10] total_population / 50
      [11] happiness / max(n_cities, 1) / 10
    """
    obs = [
        state.turn / 500.0,
        state.gold / 1000.0,
        state.happiness / 20.0,
        len(state.cities) / 10.0,
        len(state.techs_researched) / 80.0,
    ]

    if state.cities:
        c = state.cities[0]
        obs += [c.population / 20.0, len(c.built_buildings) / 20.0]
    else:
        obs += [0.0, 0.0]

    # Nuovi Fase 2
    unit_names = [u.name for u in state.units]
    obs += [
        1.0 if "Settler" in unit_names else 0.0,
        1.0 if "Scout" in unit_names else 0.0,
        state.tiles_explored / 200.0,
        sum(c.population for c in state.cities) / 50.0,
        (state.happiness / max(len(state.cities), 1)) / 10.0,
    ]

    return np.array(obs, dtype=np.float32)
```

---

## Aggiornamento: `src/envs/unciv_env.py`

### Nuovo ACTION_MAP e observation_space

```python
ACTION_MAP = {
    0: "Monument", 1: "Granary", 2: "Library", 3: "Barracks",
    4: "Settler",  5: "Warrior", 6: None,
    7: "FOUND_CITY", 8: "EXPLORE",
}

# In __init__:
self.observation_space = gym.spaces.Box(
    low=0.0, high=1.0, shape=(12,), dtype=np.float32
)
self.action_space = gym.spaces.Discrete(len(ACTION_MAP))  # 9
```

### Gestione nuove azioni in `_apply_action`

```python
def _apply_action(self, action: int) -> None:
    """Applica l'azione al save file JSON."""
    construction = ACTION_MAP[action]

    if construction is None:
        return  # Fine turno

    if construction == "FOUND_CITY":
        self._found_city()
        return

    if construction == "EXPLORE":
        self._move_scout()
        return

    # Azioni costruzione (0-5) — come Fase 1
    with open(self.save_path, 'r') as f:
        raw = json.load(f)
    for civ in raw.get("civilizations", []):
        if civ.get("civName") == "India":
            if civ.get("cities"):
                civ["cities"][0]["cityConstructions"]["currentConstruction"] = construction
            break
    with open(self.save_path, 'w') as f:
        json.dump(raw, f)


def _found_city(self) -> None:
    """
    Ordina al Settler di fondare una città.
    STUB — implementazione dipende dall'API Unciv headless.
    """
    # TODO Fase 2: trovare Settler nelle unità e impostare azione "Found City"
    pass


def _move_scout(self) -> None:
    """
    Ordina allo Scout di esplorare.
    STUB — implementazione dipende dall'API Unciv headless.
    """
    # TODO Fase 2: trovare Scout e impostare movimento verso tile inesplorata
    pass
```

---

## Aggiornamento: `src/utils/reward.py`

### Nuovi componenti reward per Fase 2

```python
# Aggiungere a REWARD_WEIGHTS
REWARD_WEIGHTS = {
    # Fase 1 — invariati
    "population_growth":  2.0,
    "building_complete":  1.5,
    "tech_researched":    3.0,
    "gold_accumulation":  0.5,
    "happiness_penalty":  0.1,
    "idle_penalty":       0.05,

    # Fase 2 — nuovi
    "new_city":           5.0,   # fondare una nuova città è molto prezioso
    "exploration":        0.1,   # ogni tile nuova esplorata
    "happiness_per_city": 0.5,   # bonus se happiness/città è buona
}


def compute_reward(prev, curr, action, weights=REWARD_WEIGHTS) -> float:
    ...
    # --- Fase 2: nuova città fondata ---
    if len(curr.cities) > len(prev.cities):
        reward += weights["new_city"]

    # --- Fase 2: esplorazione ---
    new_tiles = curr.tiles_explored - prev.tiles_explored
    if new_tiles > 0:
        reward += new_tiles * weights["exploration"]

    # --- Fase 2: happiness per città (bonus gestione) ---
    if curr.cities:
        hpc = curr.happiness / len(curr.cities)
        if hpc > 2.0:
            reward += weights["happiness_per_city"]
    ...
```

---

## Transfer Learning da Fase 1

Non ricominciare da zero — carica i pesi del modello Fase 1:

```python
# In train.py, prima di model.learn():
fase1_model_path = "models/checkpoints/fase1_final_model.zip"

if Path(fase1_model_path).exists():
    print("Transfer learning da modello Fase 1")
    model = PPO.load(fase1_model_path, env=env)
    # SB3 adatterà automaticamente l'observation space se diverso
else:
    print("Nessun modello Fase 1 trovato — training da zero")
    model = PPO(policy="MlpPolicy", env=env, ...)
```

> ⚠️ Se l'observation space cambia dimensione (da 7 a 12),
> SB3 non può caricare i pesi direttamente — serve un workaround:
> caricare solo i pesi della policy e ignorare i layer di input.
> Documentare questo caso nel WORK_LOG se si presenta.

---

## Note per Claude Code
- **Prima di implementare questa fase:** aggiornare il contratto in `CLAUDE.md`:
  `Dimensione observation vector | (12,) float32`
- `_found_city()` e `_move_scout()` sono STUB — implementarli solo dopo aver verificato
  che l'API headless di Unciv supporti questi comandi
- I test esistenti `test_parser.py` e `test_env.py` **falliranno** dopo questo aggiornamento
  perché si aspettano shape `(7,)` — aggiornarli a `(12,)` è obbligatorio
- Eseguire `python -m pytest tests/ -v` dopo ogni modifica e correggere prima di procedere
