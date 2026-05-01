import pytest
import json
import tempfile
from pathlib import Path
from src.parsers.state_parser import UncivStateParser

# Stato minimale di test
MOCK_SAVE = {
    "turns": 10,
    "currentPlayer": "India",
    "civilizations": [{
        "civName": "India",
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
    assert obs.shape == (7,)
    assert obs.dtype.name == "float32"
