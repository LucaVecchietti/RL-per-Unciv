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
    # File 24 — shape passa da (61,) a (64,): +3 feature trade-network globali.
    assert obs.shape == (64,)
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
    # File 24 — shape passa da (61,) a (64,).
    assert obs.shape == (64,)
    # x=-10, radius 10 → (-10/10 + 1)/2 = 0.0 ; y=0 → 0.5
    assert abs(obs[53] - 0.0) < 1e-5
    assert abs(obs[54] - 0.5) < 1e-5


# --- File 22 (C2) — risorse ---

def test_territory_resources_counted():
    import tempfile as _t
    civ_extra = {"cities": [{
        "name": "Delhi", "population": {"population": 1}, "cityConstructions": {},
        "tiles": [{"x": 1, "y": 1}, {"x": 2, "y": 2}], "location": {"x": 0, "y": 0},
    }]}
    tiles = [
        {"position": {"x": 1, "y": 1}, "resource": "Iron"},
        {"position": {"x": 2, "y": 2}, "resource": "Gold Ore"},
    ]
    raw = _civ_save(civ_extra, tile_list=tiles)
    parser = UncivStateParser(player_civ="India",
                              resource_types={"Iron": "Strategic", "Gold Ore": "Luxury"})
    with _t.NamedTemporaryFile(suffix=".json", mode='w', delete=False) as f:
        json.dump(raw, f)
        path = f.name
    state = parser.parse(path)
    assert state.cities[0].territory_strategic == 1
    assert state.cities[0].territory_luxury == 1
    assert state.resource_tiles[(1, 1)] == "Strategic"


def test_obs_resource_features():
    from src.parsers.state_parser import GameState, CityState
    parser = UncivStateParser()
    city = CityState("Rome", 3, "", [], 200, 0)
    city.territory_strategic = 5
    city.territory_luxury = 2
    st = GameState(10, "India", 200, 5, [city], ["Agriculture"], "Writing", 20, 20)
    obs = parser.to_observation_vector(st, selected_city=city)
    # obs[57]=territory_strategic/10=0.5 ; obs[58]=territory_luxury/10=0.2
    assert abs(obs[57] - 0.5) < 1e-5
    assert abs(obs[58] - 0.2) < 1e-5


# --- File 22 (C3) — risorse connesse ---

def test_connected_resources_counted():
    import tempfile as _t
    civ_extra = {"cities": [{
        "name": "Delhi", "population": {"population": 1}, "cityConstructions": {},
        "tiles": [{"x": 1, "y": 1}, {"x": 2, "y": 2}], "location": {"x": 0, "y": 0},
    }]}
    tiles = [
        {"position": {"x": 1, "y": 1}, "resource": "Iron", "improvement": "Mine"},  # connessa
        {"position": {"x": 2, "y": 2}, "resource": "Iron"},                          # non connessa
    ]
    raw = _civ_save(civ_extra, tile_list=tiles)
    parser = UncivStateParser(
        player_civ="India",
        resource_types={"Iron": "Strategic"},
        resource_improvements={"Iron": "Mine"},
    )
    with _t.NamedTemporaryFile(suffix=".json", mode='w', delete=False) as f:
        json.dump(raw, f)
        path = f.name
    state = parser.parse(path)
    assert state.cities[0].territory_strategic == 2
    assert state.connected_strategic == 1
    assert state.connected_luxury == 0


# --- File 23.1 — risorse Bonus e faith ---------------------------------------

def _save_with(parser: UncivStateParser, raw: dict):
    """Scrive raw su tempfile e ritorna il GameState parsato col parser dato."""
    import tempfile as _t
    with _t.NamedTemporaryFile(suffix=".json", mode='w', delete=False) as f:
        json.dump(raw, f)
        path = f.name
    return parser.parse(path)


def test_connected_bonus_count():
    """Save con tile-Bonus migliorato dal Worker → connected_bonus == 1."""
    civ_extra = {"cities": [{
        "name": "Delhi", "population": {"population": 1}, "cityConstructions": {},
        "tiles": [{"x": 3, "y": 3}], "location": {"x": 0, "y": 0},
    }]}
    tiles = [
        {"position": {"x": 3, "y": 3}, "resource": "Banana", "improvement": "Plantation"},
    ]
    raw = _civ_save(civ_extra, tile_list=tiles)
    parser = UncivStateParser(
        player_civ="India",
        resource_types={"Banana": "Bonus"},
        resource_improvements={"Banana": "Plantation"},
    )
    state = _save_with(parser, raw)
    assert state.connected_bonus == 1


def test_resource_tiles_includes_bonus():
    """tile-Bonus deve apparire in state.resource_tiles col tipo 'Bonus'."""
    tiles = [
        {"position": {"x": 4, "y": 2}, "resource": "Wheat"},
    ]
    raw = _civ_save(tile_list=tiles)
    parser = UncivStateParser(
        player_civ="India",
        resource_types={"Wheat": "Bonus"},
    )
    state = _save_with(parser, raw)
    assert (4, 2) in state.resource_tiles
    assert state.resource_tiles[(4, 2)] == "Bonus"


def test_faith_per_turn_default_zero():
    """Save senza info di fede → faith_per_turn == 0.0."""
    state = _parse_save(_civ_save())
    assert state.faith_per_turn == 0.0


def test_city_state_territory_bonus_count():
    """Città con N tile-Bonus nel proprio territorio → territory_bonus == N."""
    civ_extra = {"cities": [{
        "name": "Delhi", "population": {"population": 1}, "cityConstructions": {},
        "tiles": [{"x": 1, "y": 1}, {"x": 2, "y": 2}, {"x": 3, "y": 3}],
        "location": {"x": 0, "y": 0},
    }]}
    tiles = [
        {"position": {"x": 1, "y": 1}, "resource": "Banana"},
        {"position": {"x": 2, "y": 2}, "resource": "Wheat"},
        {"position": {"x": 3, "y": 3}, "resource": "Stone"},
    ]
    raw = _civ_save(civ_extra, tile_list=tiles)
    parser = UncivStateParser(
        player_civ="India",
        resource_types={"Banana": "Bonus", "Wheat": "Bonus", "Stone": "Bonus"},
    )
    state = _save_with(parser, raw)
    assert state.cities[0].territory_bonus == 3


# --- File 24 — campi GameState + obs trade-network ----------------------------


def test_game_state_tiles_with_road_field() -> None:
    """GameState.tiles_with_road esiste e default = set() vuoto."""
    from src.parsers.state_parser import GameState
    st = GameState(
        turn=1, current_player="India", gold=0, happiness=5,
        cities=[], techs_researched=[], current_tech=None,
        map_width=20, map_height=20,
    )
    assert hasattr(st, "tiles_with_road")
    assert st.tiles_with_road == set()


def test_game_state_cities_connected_to_capital_field() -> None:
    """GameState.cities_connected_to_capital esiste e default = 0."""
    from src.parsers.state_parser import GameState
    st = GameState(
        turn=1, current_player="India", gold=0, happiness=5,
        cities=[], techs_researched=[], current_tech=None,
        map_width=20, map_height=20,
    )
    assert hasattr(st, "cities_connected_to_capital")
    assert st.cities_connected_to_capital == 0


def test_obs_shape_64_after_file_24() -> None:
    """to_observation_vector(state).shape == (64,) dopo File 24 (+3 feature globali)."""
    from src.parsers.state_parser import GameState, CityState
    parser = UncivStateParser()
    st = GameState(
        turn=10, current_player="India", gold=200, happiness=5,
        cities=[CityState("Rome", 3, "Monument", [], 200, 0)],
        techs_researched=["Agriculture"], current_tech="Writing",
        map_width=20, map_height=20,
    )
    obs = parser.to_observation_vector(st)
    assert obs.shape == (64,)


def test_obs_connected_cities_ratio() -> None:
    """obs[61] = connected_cities_ratio = città non-capitale connesse / totale non-capitali.

    Setup: 3 città (1 capitale + 2 non-capitale), 1 non-capitale connessa.
    Ratio atteso = 1/2 = 0.5.
    """
    from src.parsers.state_parser import GameState, CityState
    parser = UncivStateParser()
    cities = [
        CityState("Rome", 5, "Monument", [], 200, 0),   # capitale
        CityState("Delhi", 3, "", [], 200, 0),          # non-capitale connessa
        CityState("Mumbai", 3, "", [], 200, 0),         # non-capitale non connessa
    ]
    st = GameState(
        turn=10, current_player="India", gold=200, happiness=5,
        cities=cities, techs_researched=[], current_tech=None,
        map_width=20, map_height=20,
    )
    st.cities_connected_to_capital = 1
    obs = parser.to_observation_vector(st)
    assert abs(obs[61] - 0.5) < 1e-5


def test_obs_roads_built_count_norm() -> None:
    """obs[62] = roads_built_count / 50.0.

    tiles_with_road con 10 elementi → 10/50 = 0.2.
    """
    from src.parsers.state_parser import GameState, CityState
    parser = UncivStateParser()
    st = GameState(
        turn=10, current_player="India", gold=200, happiness=5,
        cities=[CityState("Rome", 3, "Monument", [], 200, 0)],
        techs_researched=[], current_tech=None,
        map_width=20, map_height=20,
    )
    st.tiles_with_road = {(i, 0) for i in range(10)}
    obs = parser.to_observation_vector(st)
    assert abs(obs[62] - 0.2) < 1e-5


def test_obs_selected_unit_on_road_true() -> None:
    """obs[63] = 1.0 se Worker selezionato sta su tile con road."""
    from src.parsers.state_parser import GameState, CityState, UnitState
    parser = UncivStateParser()
    st = GameState(
        turn=10, current_player="India", gold=200, happiness=5,
        cities=[CityState("Rome", 3, "Monument", [], 200, 0)],
        techs_researched=[], current_tech=None,
        map_width=20, map_height=20,
    )
    st.tiles_with_road = {(2, 3)}
    worker = UnitState("Worker", x=2, y=3, movement_points=2.0, id=42)
    obs = parser.to_observation_vector(st, selected_unit=worker)
    assert abs(obs[63] - 1.0) < 1e-5


def test_obs_selected_unit_on_road_false() -> None:
    """obs[63] = 0.0 se Worker selezionato NON è su tile con road."""
    from src.parsers.state_parser import GameState, CityState, UnitState
    parser = UncivStateParser()
    st = GameState(
        turn=10, current_player="India", gold=200, happiness=5,
        cities=[CityState("Rome", 3, "Monument", [], 200, 0)],
        techs_researched=[], current_tech=None,
        map_width=20, map_height=20,
    )
    st.tiles_with_road = {(5, 5)}
    worker = UnitState("Worker", x=2, y=3, movement_points=2.0, id=42)
    obs = parser.to_observation_vector(st, selected_unit=worker)
    assert abs(obs[63] - 0.0) < 1e-5
