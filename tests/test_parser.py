import pytest
import json
import tempfile
from pathlib import Path
from src.parsers.state_parser import UncivStateParser

# Stato minimale di test — formato reale Unciv save JSON
MOCK_SAVE = {
    "turns": 10,
    "currentPlayer": "India",
    "civilizations": [{
        "civName": "India",
        "gold": 200,
        "statsHistory": {"10": "S30N5C10P8G20T7F28H8W1A0"},
        "cities": [{
            "name": "Rome",
            "population": {"population": 3, "foodStored": 12},
            "cityConstructions": {
                "constructionQueue": ["Monument"],
                "inProgressConstructions": {"Monument": 30},
                "builtBuildings": ["Granary"]
            },
            "health": 200,
            "tiles": ["a", "b", "c"],
            "workedTiles": ["a", "b"],
            "location": {"x": 5, "y": 7}
        }],
        "tech": {
            "techsResearched": ["Agriculture", "Mining"],
            "techsInProgress": {"Writing": 20}
        },
        "diplomacy": {},
        "proximity": {}
    }],
    "tileMap": {
        "mapParameters": {"mapSize": {"width": 20, "height": 20}},
        "tileList": []
    }
}

def test_parse_basic():
    parser = UncivStateParser(player_civ="India")
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
        turn=10, current_player="India", gold=200, happiness=5,
        cities=[CityState("Rome", 3, "Monument", ["Granary"], 200, 0)],
        techs_researched=["Agriculture"], current_tech="Writing",
        map_width=20, map_height=20
    )
    obs = parser.to_observation_vector(mock_state)
    assert obs.shape == (57,)
    assert obs.dtype.name == "float32"


# --- File 19 — extended metrics logging ---

def _parse_save(raw: dict):
    """Scrive un save dict su file temporaneo e lo parsa come civ India."""
    parser = UncivStateParser(player_civ="India")
    with tempfile.NamedTemporaryFile(suffix=".json", mode='w', delete=False) as f:
        json.dump(raw, f)
        tmp_path = f.name
    return parser.parse(tmp_path)


def _civ_save(civ_extra: dict | None = None, tile_list: list | None = None) -> dict:
    """Costruisce un save minimale con un solo civ India, estendibile via civ_extra."""
    civ = {
        "civName": "India",
        "gold": 100,
        "statsHistory": {},
        "cities": [],
        "tech": {},
        "diplomacy": {},
        "proximity": {},
    }
    if civ_extra:
        civ.update(civ_extra)
    return {
        "turns": 5,
        "currentPlayer": "India",
        "civilizations": [civ],
        "tileMap": {
            "mapParameters": {"mapSize": {"width": 20, "height": 20}},
            "tileList": tile_list or [],
        },
    }


def test_tiles_explored_empty_civ():
    state = _parse_save(_civ_save())
    assert state.tiles_explored == 0


def test_tiles_explored_count():
    tiles = [{"position": {"x": i, "y": 0}, "exploredBy": ["India"]} for i in range(10)]
    state = _parse_save(_civ_save(tile_list=tiles))
    assert state.tiles_explored == 10


def test_city_territory_tiles():
    civ_extra = {"cities": [{
        "name": "Delhi",
        "population": {"population": 1},
        "cityConstructions": {},
        "tiles": ["a", "b", "c", "d", "e", "f", "g"],
        "location": {"x": 0, "y": 0},
    }]}
    state = _parse_save(_civ_save(civ_extra))
    assert state.city_territory_tiles == 7


def test_strategic_resources_parsed():
    civ_extra = {"detailedCivResources": [
        {"resource": {"name": "Iron", "resourceType": "Strategic"}, "amount": 2},
    ]}
    state = _parse_save(_civ_save(civ_extra))
    assert state.strategic_resources == {"Iron": 2}


def test_luxury_resources_parsed():
    civ_extra = {"detailedCivResources": [
        {"resource": {"name": "Silk", "resourceType": "Luxury"}, "amount": 1},
    ]}
    state = _parse_save(_civ_save(civ_extra))
    assert state.luxury_resources == {"Silk": 1}


def test_science_per_turn_from_history():
    civ_extra = {"tech": {"scienceOfLast8Turns": [5, 8, 10]}}
    state = _parse_save(_civ_save(civ_extra))
    assert state.science_per_turn == 10.0


# --- File 20 — fix decodifica statsHistory ---

def _city_dict(name: str = "Delhi") -> dict:
    return {
        "name": name,
        "population": {"population": 1},
        "cityConstructions": {},
        "tiles": [],
        "location": {"x": 0, "y": 0},
    }


def test_statshistory_happiness_from_H():
    state = _parse_save(_civ_save({"statsHistory": {"5": "H6"}}))
    assert state.happiness == 6.0


def test_statshistory_food_and_production_to_main_city():
    civ_extra = {"statsHistory": {"5": "C4P7"}, "cities": [_city_dict()]}
    state = _parse_save(_civ_save(civ_extra))
    assert state.cities[0].food_per_turn == 4.0
    assert state.cities[0].production_per_turn == 7.0


def test_culture_per_turn_not_from_statshistory_C():
    # C è il cibo (Growth), NON deve diventare cultura/turno
    state = _parse_save(_civ_save({"statsHistory": {"5": "C99"}}))
    assert state.culture_per_turn == 0.0


def test_gold_per_turn_not_from_population_N():
    # N è la popolazione, NON deve diventare oro/turno
    state = _parse_save(_civ_save({"statsHistory": {"5": "N50"}}))
    assert state.gold_per_turn == 0.0


def test_stored_culture_parsed():
    state = _parse_save(_civ_save({"policies": {"storedCulture": 42}}))
    assert state.stored_culture == 42.0


# --- File 21 — unit id + normalizzazione coordinate hex ---

def test_unitstate_has_id():
    tiles = [{
        "position": {"x": 1, "y": 1},
        "militaryUnit": {"owner": "India", "name": "Warrior", "currentMovement": 2, "id": 7},
    }]
    state = _parse_save(_civ_save(tile_list=tiles))
    assert len(state.units) == 1
    assert state.units[0].id == 7


def test_coord_normalization_handles_negative():
    from src.parsers.state_parser import GameState, UnitState
    parser = UncivStateParser()
    st = GameState(
        turn=1, current_player="India", gold=0, happiness=5,
        cities=[], techs_researched=[], current_tech=None,
        map_width=23, map_height=15, map_radius=10, units=[],
    )
    sel = UnitState("Warrior", x=-10, y=0, movement_points=2.0, id=1)
    obs = parser.to_observation_vector(st, selected_unit=sel)
    assert obs.shape == (57,)
    # x=-10, radius 10 → (-10/10 + 1)/2 = 0.0 ; y=0 → 0.5
    assert abs(obs[53] - 0.0) < 1e-5
    assert abs(obs[54] - 0.5) < 1e-5
