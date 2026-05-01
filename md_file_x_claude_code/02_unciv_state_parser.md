# 02 — Unciv State Parser

## Obiettivo
Costruire il modulo che legge e interpreta i file di salvataggio JSON di Unciv,
estraendo le informazioni rilevanti per l'agente RL.

---

## Come funziona il salvataggio di Unciv

Unciv salva le partite in file JSON compressi (`.unciv` o `.json`) nella cartella:
- **Android:** `/Android/data/com.unciv.app/files/saves/`
- **Desktop:** `~/.local/share/Unciv/saves/` (Linux) o `%APPDATA%/Unciv/saves/` (Windows)

Il file JSON ha questa struttura ad alto livello:
```json
{
  "gameId": "...",
  "turns": 42,
  "civilizations": [...],
  "tileMap": { "tileList": [...] },
  "currentPlayer": "Romans",
  "difficulty": "Prince"
}
```

---

## Struttura dati chiave da estrarre

### Civilizzazione (il nostro agente)
```json
{
  "civName": "Romans",
  "cities": [...],
  "tech": { "techsResearched": [...], "currentTechnology": "Writing" },
  "policies": { "adoptedPolicies": [...] },
  "gold": 150,
  "happiness": 8,
  "militaryUnits": [...],
  "diplomaticStatus": {...}
}
```

### Città
```json
{
  "name": "Rome",
  "population": { "population": 5 },
  "cityConstructions": {
    "currentConstructionIsUserSet": true,
    "currentConstruction": "Monument",
    "builtBuildings": ["Monument", "Granary"]
  },
  "tiles": [...],
  "health": 200
}
```

### Tile (cella mappa)
```json
{
  "position": { "x": 3, "y": -2 },
  "baseTerrain": "Grassland",
  "terrainFeatures": ["Forest"],
  "resource": "Wheat",
  "improvement": "Farm",
  "militaryUnit": null,
  "civilianUnit": null,
  "exploredBy": ["Romans"]
}
```

---

## Implementazione: `src/parsers/state_parser.py`

```python
import json
import gzip
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class CityState:
    name: str
    population: int
    current_construction: str
    built_buildings: list[str]
    health: int
    tiles_count: int

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
    # Aggiungere altri campi nelle fasi successive

class UncivStateParser:
    """
    Legge un file di salvataggio Unciv (JSON o JSON.gz)
    e lo converte in strutture dati Python usabili dall'ambiente RL.
    """

    def __init__(self, player_civ: str = "Romans"):
        self.player_civ = player_civ

    def load(self, path: str | Path) -> dict:
        """Carica il file JSON raw, gestendo sia plain che gzip."""
        path = Path(path)
        try:
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                return json.load(f)
        except gzip.BadGzipFile:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)

    def parse(self, path: str | Path) -> GameState:
        """Entry point principale: path → GameState."""
        raw = self.load(path)
        return self._extract_game_state(raw)

    def _extract_game_state(self, raw: dict) -> GameState:
        civ_data = self._find_player_civ(raw)
        cities = [self._parse_city(c) for c in civ_data.get("cities", [])]
        tech = civ_data.get("tech", {})

        return GameState(
            turn=raw.get("turns", 0),
            current_player=raw.get("currentPlayer", ""),
            gold=civ_data.get("gold", 0),
            happiness=civ_data.get("happiness", 0),
            cities=cities,
            techs_researched=tech.get("techsResearched", []),
            current_tech=tech.get("currentTechnology"),
            map_width=raw.get("tileMap", {}).get("mapParameters", {}).get("mapSize", {}).get("width", 0),
            map_height=raw.get("tileMap", {}).get("mapParameters", {}).get("mapSize", {}).get("height", 0),
        )

    def _find_player_civ(self, raw: dict) -> dict:
        for civ in raw.get("civilizations", []):
            if civ.get("civName") == self.player_civ:
                return civ
        raise ValueError(f"Civilizzazione '{self.player_civ}' non trovata nel save file")

    def _parse_city(self, city_raw: dict) -> CityState:
        constructions = city_raw.get("cityConstructions", {})
        return CityState(
            name=city_raw.get("name", ""),
            population=city_raw.get("population", {}).get("population", 1),
            current_construction=constructions.get("currentConstruction", ""),
            built_buildings=constructions.get("builtBuildings", []),
            health=city_raw.get("health", 200),
            tiles_count=len(city_raw.get("tiles", [])),
        )

    def to_observation_vector(self, state: GameState) -> np.ndarray:
        """
        Converte GameState in un vettore numpy flat per l'agente RL.
        FASE 1: solo metriche base.
        Da espandere nelle fasi successive.
        """
        obs = [
            state.turn / 500.0,               # normalizzato
            state.gold / 1000.0,
            state.happiness / 20.0,
            len(state.cities) / 10.0,
            len(state.techs_researched) / 80.0,
        ]
        # Aggiunge dati prima città (padding se non esiste)
        if state.cities:
            c = state.cities[0]
            obs += [
                c.population / 20.0,
                len(c.built_buildings) / 20.0,
            ]
        else:
            obs += [0.0, 0.0]

        return np.array(obs, dtype=np.float32)
```

---

## Test: `tests/test_parser.py`

```python
import pytest
import json
import tempfile
from pathlib import Path
from src.parsers.state_parser import UncivStateParser

# Stato minimale di test
MOCK_SAVE = {
    "turns": 10,
    "currentPlayer": "Romans",
    "civilizations": [{
        "civName": "Romans",
        "gold": 200,
        "happiness": 5,
        "cities": [{
            "name": "Rome",
            "population": {"population": 3},
            "cityConstructions": {
                "currentConstruction": "Monument",
                "builtBuildings": ["Granary"]
            },
            "health": 200,
            "tiles": []
        }],
        "tech": {
            "techsResearched": ["Agriculture", "Mining"],
            "currentTechnology": "Writing"
        }
    }],
    "tileMap": {"mapParameters": {"mapSize": {"width": 20, "height": 20}}}
}

def test_parse_basic():
    parser = UncivStateParser(player_civ="Romans")
    with tempfile.NamedTemporaryFile(suffix=".json", mode='w', delete=False) as f:
        json.dump(MOCK_SAVE, f)
        tmp_path = f.name

    state = parser.parse(tmp_path)
    assert state.turn == 10
    assert state.gold == 200
    assert len(state.cities) == 1
    assert state.cities[0].name == "Rome"

def test_observation_vector_shape():
    parser = UncivStateParser()
    state = parser.parse.__wrapped__ if hasattr(parser.parse, '__wrapped__') else None
    # Test diretto su to_observation_vector
    from src.parsers.state_parser import GameState, CityState
    mock_state = GameState(
        turn=10, current_player="Romans", gold=200, happiness=5,
        cities=[CityState("Rome", 3, "Monument", ["Granary"], 200, 0)],
        techs_researched=["Agriculture"], current_tech="Writing",
        map_width=20, map_height=20
    )
    obs = parser.to_observation_vector(mock_state)
    assert obs.shape == (7,)
    assert obs.dtype.name == "float32"
```

---

## Note per Claude Code
- Il metodo `to_observation_vector` è il **contratto** tra parser e ambiente: qualsiasi modifica alla dimensione del vettore deve essere aggiornata anche in `unciv_env.py` (file 03)
- Per la Fase 1 il vettore ha **7 elementi** — documentare sempre la dimensione nei commenti
- Gestire sempre il caso `cities = []` (turno 1, prima della fondazione)
- Non usare `pandas` — solo `numpy` per mantenere le dipendenze leggere
