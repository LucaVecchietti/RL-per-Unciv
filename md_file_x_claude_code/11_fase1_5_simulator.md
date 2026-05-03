# 11 — Fase 1.5: Micro-Simulatore Python

## Obiettivo
Sostituire lo stub `_advance_turn()` con un simulatore Python fedele alle
formule di Unciv, così l'agente riceve reward reali e il training produce
una policy non-random.

---

## Posizione nella sequenza dei file

```
File 01-07  → Completati (Sessioni 1-7) ✅
File 08     → NON ancora eseguito — Headless Integration (Fase 2)
File 09     → NON ancora eseguito — Expansion, obs (12,), UnitState (Fase 2)
File 10     → NON ancora eseguito — Obs Space Migration (Fase 2)

► File 11   → QUESTO FILE — Fase 1.5 simulatore Python
  File 12   → Fix race condition env_rank
  File 13   → Diagnostica training

File 08-10  → Eseguire SOLO dopo che Fase 1.5 è completa e modello salvato
```

> ⚠️ I file 08, 09, 10 aggiungono `UncivHeadless`, `UnitState`, `tiles_explored`
> e fanno salire obs a `(12,)`. **NON eseguirli durante la Fase 1.5.**
> Questo file mantiene tutti i contratti invariati: obs `(7,)`, azioni `7`,
> `GameState` senza `units`/`tiles_explored`.

---

## Confronto approcci

| Approccio | Throughput | Dipendenze | Reward reale |
|---|---|---|---|
| Stub JSON (attuale) | ~500 step/s | nessuna | ❌ reward ~0 |
| **Simulatore Python (questo file)** | **~300-500 step/s** | **nessuna** | **✅ sì** |
| Unciv headless (File 08) | ~1-2 step/s | Java + JAR | ✅ sì |

Il simulatore permette di arrivare a 500k-1M step in ~1 ora, validare che PPO
impari davvero, poi fare fine-tuning su headless reale (~100k step, ~8-12 ore).

---

## Contratti invariati in questa fase

| Contratto | Valore | Cambia con |
|---|---|---|
| Obs vector shape | `(7,)` float32 | File 09/10 |
| Numero azioni | `7` (Discrete) | File 09/10 |
| `GameState` campi | invariati | File 09 (aggiunge `units`, `tiles_explored`) |
| `_advance_turn` | usa `UncivSimulator` | File 08 (usa `UncivHeadless`) |

---

## File da creare e modificare

| Azione | File | Cosa fare |
|---|---|---|
| **Creare** | `src/utils/simulator.py` | Nuovo — logica simulazione |
| **Modificare** | `src/envs/unciv_env.py` | Solo 3 modifiche puntuali (vedi sotto) |
| **Creare** | `tests/test_simulator.py` | Nuovo — test formule |
| **Modificare** | `WORK_LOG.md` | Aggiornare al termine |
| **Modificare** | `CLAUDE.md` | Fase 1.5 → in progress |

> ⚠️ NON aggiungere `UncivHeadless` né il suo import — arriverà con file `08`.
> NON modificare `GameState` — arriverà con file `09`.
> NON modificare `observation_space` né `action_space`.

---

## Formule Unciv (Kotlin → Python)

Fonti: `CityStats.kt`, `PopulationManager.kt`, `TechManager.kt`, `CityConstructions.kt`

### Produzione
```python
CONSTRUCTION_COSTS = {
    "Monument": 60, "Granary": 60, "Library": 90,
    "Barracks": 70, "Settler": 106, "Warrior": 40,
}
# produzione/turno = 3 (base) + max(0, population - 1) (workers bonus)
# accumulo → completamento → builtBuildings.append(), productionAccumulated = 0
```

### Crescita Popolazione
```python
food_per_turn = 2 + (2 if "Granary" in built else 0)
food_threshold = 10 + (population * 3)   # pop=1→13, pop=2→16, pop=3→19
# storedFood += food_per_turn; se >= threshold: population += 1, storedFood = 0
```

### Scienza
```python
TECH_COSTS = {
    "Agriculture": 20, "Mining": 35, "Writing": 55, "Pottery": 35,
    "Animal Husbandry": 35, "Archery": 35, "Bronze Working": 55,
    "Sailing": 55, "Trapping": 55, "The Wheel": 55,
    "Masonry": 55, "Calendar": 70, "Mathematics": 100,
}
science_per_turn = 2 + (2 if "Library" in all_buildings else 0)
                     + int(total_population * 0.5)
```

### Oro
```python
gold_per_turn = len(cities) * 1   # 1 oro per città base
```

### Happiness
```python
# base = 9.0 (Chieftain), monument_bonus = +1.0, pop_penalty = -max(0, (pop-1)*0.5)
```

---

## Implementazione: `src/utils/simulator.py`

```python
"""
Micro-simulatore Python per Unciv — Fase 1.5.
Sostituito da UncivHeadless (src/utils/headless.py) nella Fase 2 (file 08).
"""
from __future__ import annotations
from typing import Optional

CONSTRUCTION_COSTS: dict[str, int] = {
    "Monument": 60, "Granary": 60, "Library": 90,
    "Barracks": 70, "Settler": 106, "Warrior": 40,
}

TECH_COSTS: dict[str, int] = {
    "Agriculture": 20, "Mining": 35, "Writing": 55, "Pottery": 35,
    "Animal Husbandry": 35, "Archery": 35, "Bronze Working": 55,
    "Sailing": 55, "Trapping": 55, "The Wheel": 55,
    "Masonry": 55, "Calendar": 70, "Mathematics": 100,
}

TECH_TREE: list[str] = [
    "Agriculture", "Pottery", "Animal Husbandry", "Mining",
    "Archery", "Writing", "Bronze Working", "The Wheel",
    "Masonry", "Trapping", "Sailing", "Calendar", "Mathematics",
]


class UncivSimulator:
    """
    Simula un turno Unciv aggiornando il dizionario raw JSON.
    Indipendente da Unciv.jar. Usato in Fase 1.5.
    """
    PLAYER_CIV: str = "India"

    def advance_turn(self, raw: dict) -> dict:
        """Avanza di un turno il save file raw. Modifica in-place e ritorna."""
        civ = self._get_civ(raw)
        if not civ:
            return raw
        cities = civ.get("cities", [])
        tech_data = civ.get("tech", {})
        for city in cities:
            self._simulate_production(city)
            self._simulate_population(city)
        self._simulate_science(civ, tech_data)
        self._simulate_gold(civ, cities)
        self._simulate_happiness(civ, cities)
        raw["turns"] = raw.get("turns", 0) + 1
        return raw

    def _simulate_production(self, city: dict) -> None:
        constructions = city.setdefault("cityConstructions", {})
        built = constructions.setdefault("builtBuildings", [])
        current = constructions.get("currentConstruction", "")
        if not current or current not in CONSTRUCTION_COSTS:
            return
        population = city.get("population", {}).get("population", 1)
        production = 3 + max(0, population - 1)
        constructions["productionAccumulated"] = (
            constructions.get("productionAccumulated", 0) + production
        )
        if constructions["productionAccumulated"] >= CONSTRUCTION_COSTS[current]:
            if current not in built:
                built.append(current)
            constructions["productionAccumulated"] = 0
            constructions["currentConstruction"] = ""

    def _simulate_population(self, city: dict) -> None:
        pop_data = city.setdefault("population", {})
        population = pop_data.get("population", 1)
        built = city.get("cityConstructions", {}).get("builtBuildings", [])
        food_per_turn = 2 + (2 if "Granary" in built else 0)
        food_threshold = 10 + (population * 3)
        pop_data["storedFood"] = pop_data.get("storedFood", 0) + food_per_turn
        if pop_data["storedFood"] >= food_threshold:
            pop_data["population"] = population + 1
            pop_data["storedFood"] = 0

    def _simulate_science(self, civ: dict, tech_data: dict) -> None:
        cities = civ.get("cities", [])
        total_pop = sum(c.get("population", {}).get("population", 1) for c in cities)
        all_buildings = self._get_all_buildings(cities)
        science = 2 + (2 if "Library" in all_buildings else 0) + int(total_pop * 0.5)
        tech_data["scienceAccumulated"] = tech_data.get("scienceAccumulated", 0) + science
        current_tech = tech_data.get("currentTechnology")
        if current_tech:
            cost = TECH_COSTS.get(current_tech, 55)
            if tech_data["scienceAccumulated"] >= cost:
                researched = tech_data.setdefault("techsResearched", [])
                if current_tech not in researched:
                    researched.append(current_tech)
                tech_data["scienceAccumulated"] = 0
                tech_data["currentTechnology"] = self._next_tech(researched)

    def _next_tech(self, researched: list[str]) -> Optional[str]:
        for tech in TECH_TREE:
            if tech not in researched:
                return tech
        return None

    def _simulate_gold(self, civ: dict, cities: list[dict]) -> None:
        civ["gold"] = civ.get("gold", 0) + len(cities)

    def _simulate_happiness(self, civ: dict, cities: list[dict]) -> None:
        all_buildings = self._get_all_buildings(cities)
        total_pop = sum(c.get("population", {}).get("population", 1) for c in cities)
        civ["happiness"] = (
            9.0
            + (1.0 if "Monument" in all_buildings else 0.0)
            - max(0.0, (total_pop - 1) * 0.5)
        )

    def _get_civ(self, raw: dict) -> Optional[dict]:
        for civ in raw.get("civilizations", []):
            if civ.get("civName") == self.PLAYER_CIV:
                return civ
        return None

    def _get_all_buildings(self, cities: list[dict]) -> set[str]:
        buildings: set[str] = set()
        for city in cities:
            buildings.update(city.get("cityConstructions", {}).get("builtBuildings", []))
        return buildings
```

---

## Le 3 modifiche a `src/envs/unciv_env.py`

**Solo queste tre — nient'altro.**

### Modifica 1: import (aggiungere dopo gli import esistenti)
```python
from src.utils.simulator import UncivSimulator
```

### Modifica 2: `__init__` (aggiungere dopo `self.parser = UncivStateParser(...)`)
```python
self.simulator = UncivSimulator()
```

### Modifica 3: sostituire `_advance_turn`
```python
def _advance_turn(self) -> None:
    """
    Fase 1.5: micro-simulatore Python.
    Fase 2 (file 08): sostituire con self.headless.advance_turn(self.save_path).
    """
    with open(self.save_path, 'r') as f:
        raw = json.load(f)
    raw = self.simulator.advance_turn(raw)
    with open(self.save_path, 'w') as f:
        json.dump(raw, f)
```

---

## Test: `tests/test_simulator.py`

```python
import pytest
from src.utils.simulator import UncivSimulator, CONSTRUCTION_COSTS, TECH_COSTS


@pytest.fixture
def sim():
    return UncivSimulator()

@pytest.fixture
def save():
    return {
        "turns": 2,
        "civilizations": [{
            "civName": "India",
            "gold": 50.0, "happiness": 9.0,
            "cities": [{
                "name": "Delhi",
                "population": {"population": 1, "storedFood": 0},
                "cityConstructions": {
                    "currentConstruction": "Monument",
                    "builtBuildings": [],
                    "productionAccumulated": 0,
                },
                "health": 200, "tiles": [],
            }],
            "tech": {"techsResearched": ["Agriculture"],
                     "currentTechnology": "Pottery",
                     "scienceAccumulated": 0}
        }]
    }

def test_turn_increments(sim, save):
    sim.advance_turn(save)
    assert save["turns"] == 3

def test_production_accumulates(sim, save):
    sim.advance_turn(save)
    acc = save["civilizations"][0]["cities"][0]["cityConstructions"]["productionAccumulated"]
    assert acc > 0

def test_building_completes(sim, save):
    cc = save["civilizations"][0]["cities"][0]["cityConstructions"]
    cc["productionAccumulated"] = CONSTRUCTION_COSTS["Monument"] - 2
    sim.advance_turn(save)
    assert "Monument" in cc["builtBuildings"]

def test_construction_cleared_on_completion(sim, save):
    cc = save["civilizations"][0]["cities"][0]["cityConstructions"]
    cc["productionAccumulated"] = CONSTRUCTION_COSTS["Monument"] - 2
    sim.advance_turn(save)
    assert cc["currentConstruction"] == ""

def test_food_accumulates(sim, save):
    pop = save["civilizations"][0]["cities"][0]["population"]
    sim.advance_turn(save)
    assert pop["storedFood"] > 0

def test_population_grows(sim, save):
    pop = save["civilizations"][0]["cities"][0]["population"]
    pop["storedFood"] = 11  # +2/turn → 13 >= threshold(1)=13
    sim.advance_turn(save)
    assert pop["population"] == 2

def test_granary_bonus_food(sim, save):
    city = save["civilizations"][0]["cities"][0]
    city["cityConstructions"]["builtBuildings"] = ["Granary"]
    city["population"]["storedFood"] = 0
    sim.advance_turn(save)
    assert city["population"]["storedFood"] == 4  # 2+2

def test_science_accumulates(sim, save):
    tech = save["civilizations"][0]["tech"]
    sim.advance_turn(save)
    assert tech["scienceAccumulated"] > 0

def test_tech_researched(sim, save):
    tech = save["civilizations"][0]["tech"]
    tech["scienceAccumulated"] = TECH_COSTS["Pottery"] - 1
    sim.advance_turn(save)
    assert "Pottery" in tech["techsResearched"]

def test_next_tech_assigned(sim, save):
    tech = save["civilizations"][0]["tech"]
    tech["scienceAccumulated"] = TECH_COSTS["Pottery"] - 1
    sim.advance_turn(save)
    assert tech["currentTechnology"] not in (None, "Pottery")

def test_gold_increases(sim, save):
    civ = save["civilizations"][0]
    before = civ["gold"]
    sim.advance_turn(save)
    assert civ["gold"] > before

def test_happiness_base(sim, save):
    civ = save["civilizations"][0]
    civ["happiness"] = 0
    sim.advance_turn(save)
    assert civ["happiness"] == pytest.approx(9.0)

def test_monument_happiness_bonus(sim, save):
    civ = save["civilizations"][0]
    civ["cities"][0]["cityConstructions"]["builtBuildings"] = ["Monument"]
    sim.advance_turn(save)
    assert civ["happiness"] == pytest.approx(10.0)

def test_population_happiness_penalty(sim, save):
    civ = save["civilizations"][0]
    civ["cities"][0]["population"]["population"] = 3
    sim.advance_turn(save)
    assert civ["happiness"] == pytest.approx(8.0)  # 9 - (3-1)*0.5
```

---

## Checklist esecuzione

```
Step 1  → Leggi CLAUDE.md e WORK_LOG.md
Step 2  → Salva modello:
          Copy-Item "models\checkpoints\best\best_model.zip"
                    "models\checkpoints\fase1_pretrain.zip"
Step 3  → Crea src/utils/simulator.py
Step 4  → pytest tests/test_simulator.py -v  ← tutti devono passare
Step 5  → Modifica unciv_env.py (SOLO le 3 modifiche indicate)
Step 6  → pytest tests/ -v  ← tutti i 29+ test devono passare
Step 7  → python train.py   ← rilancia training da zero
Step 8  → TensorBoard: ep_rew_mean deve salire entro 50k step
Step 9  → Aggiorna WORK_LOG.md
Step 10 → git add -A && git commit -m "feat: micro-simulatore Python Fase 1.5" && git push
```

**Procedere al file 12 (env_rank) subito dopo. File 08-10 solo dopo modello salvato.**

---

## Segnali di successo

| Metrica | Dopo 100k step | Dopo 500k step |
|---|---|---|
| `ep_rew_mean` | > 0.0 | > 2.0 |
| `unciv/happiness_mean` | ~9-10 | ~9-10 stabile |
| `unciv/gold_mean` | cresce | > 100 |
| distribuzione azioni | non uniforme | preferenza 1-2 azioni |

---

## Note per Claude Code
- `UncivSimulator` è completamente indipendente da Unciv.jar
- `GameState` e `state_parser.py` rimangono invariati — nessuna aggiunta di campi
- Se `_get_civ()` ritorna `None`, `advance_turn` ritorna `raw` senza eccezioni (fail-safe)
- Il commento `Fase 2 (file 08): sostituire con...` in `_advance_turn` è
  intenzionale — serve come reminder per la sessione successiva
