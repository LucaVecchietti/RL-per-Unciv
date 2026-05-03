import json
import zipfile

import pytest

from src.utils.ruleset_reader import ConstructionInfo, load_early_game_constructions

_MOCK_TECHS = [
    {
        "era": "Ancient",
        "techs": [
            {"name": "Agriculture"},
            {"name": "Bronze Working"},
            {"name": "Pottery"},
            {"name": "Writing"},
            {"name": "Masonry"},
            {"name": "Animal Husbandry"},
        ],
    },
    {
        "era": "Classical",
        "techs": [
            {"name": "Philosophy"},
            {"name": "Iron Working"},
            {"name": "Mathematics"},
            {"name": "Construction"},
        ],
    },
    {
        "era": "Medieval",
        "techs": [
            {"name": "Currency"},
            {"name": "Chivalry"},
        ],
    },
]

_MOCK_BUILDINGS = [
    {"name": "Monument"},
    {"name": "Barracks", "requiredTech": "Bronze Working"},
    {"name": "Granary", "requiredTech": "Pottery"},
    {"name": "Library", "requiredTech": "Writing"},
    {"name": "Walls", "requiredTech": "Masonry"},
    {"name": "Temple", "requiredTech": "Philosophy"},
    {"name": "Colosseum", "requiredTech": "Construction"},
    {"name": "Courthouse", "requiredTech": "Writing"},
    {"name": "Stable", "requiredTech": "Animal Husbandry"},
    # wonders
    {"name": "Stonehenge", "isWonder": True, "requiredTech": "Masonry"},
    {"name": "Great Library", "isWonder": True, "requiredTech": "Writing"},
    {"name": "Colossus", "isWonder": True, "requiredTech": "Bronze Working"},
    # national wonders
    {"name": "National College", "isNationalWonder": True, "requiredTech": "Philosophy"},
    {"name": "National Epic", "isNationalWonder": True},
    # civ-unique
    {"name": "Krepost", "requiredTech": "Bronze Working"},
    {"name": "Burial Tomb"},
    # Medieval — excluded by era
    {"name": "Market", "requiredTech": "Currency"},
]

_MOCK_UNITS = [
    {"name": "Warrior", "unitType": "Sword"},
    {"name": "Scout", "unitType": "Scout"},
    {"name": "Settler", "unitType": "Civilian"},
    {"name": "Worker", "unitType": "Civilian"},
    {"name": "Spearman", "unitType": "Sword", "requiredTech": "Bronze Working"},
    # Great People — excluded
    {"name": "Great Scientist", "unitType": "Civilian"},
    {"name": "Great Artist", "unitType": "Civilian"},
    # water — excluded by unitType
    {"name": "Trireme", "unitType": "Ranged Water", "requiredTech": "Optics"},
    {"name": "Galley", "unitType": "Melee Water"},
    # civ-unique — excluded
    {"name": "Maori Warrior", "unitType": "Sword"},
    {"name": "Jaguar", "unitType": "Sword"},
]


@pytest.fixture
def mock_jar(tmp_path):
    jar_path = tmp_path / "Unciv.jar"
    with zipfile.ZipFile(jar_path, "w") as zf:
        zf.writestr("jsons/Civ V - Vanilla/Techs.json", json.dumps(_MOCK_TECHS))
        zf.writestr("jsons/Civ V - Vanilla/Buildings.json", json.dumps(_MOCK_BUILDINGS))
        zf.writestr("jsons/Civ V - Vanilla/Units.json", json.dumps(_MOCK_UNITS))
    return str(jar_path)


@pytest.fixture
def constructions(mock_jar):
    return load_early_game_constructions(mock_jar)


def _names(constructions: list[ConstructionInfo]) -> set[str]:
    return {c.name for c in constructions}


def test_load_returns_monument(constructions):
    monument = next((c for c in constructions if c.name == "Monument"), None)
    assert monument is not None
    assert monument.required_tech is None
    assert monument.is_unit is False


def test_load_returns_barracks(constructions):
    barracks = next((c for c in constructions if c.name == "Barracks"), None)
    assert barracks is not None
    assert barracks.required_tech == "Bronze Working"
    assert barracks.is_unit is False


def test_no_wonders_included(constructions):
    names = _names(constructions)
    assert "Stonehenge" not in names
    assert "Great Library" not in names
    assert "Colossus" not in names


def test_no_national_wonders(constructions):
    names = _names(constructions)
    assert "National College" not in names
    assert "National Epic" not in names


def test_no_civ_unique_buildings(constructions):
    names = _names(constructions)
    assert "Krepost" not in names
    assert "Burial Tomb" not in names


def test_no_medieval_buildings(constructions):
    assert "Market" not in _names(constructions)


def test_warrior_is_unit(constructions):
    warrior = next((c for c in constructions if c.name == "Warrior"), None)
    assert warrior is not None
    assert warrior.is_unit is True
    assert warrior.required_tech in (None, "Agriculture")


def test_no_great_people(constructions):
    names = _names(constructions)
    assert "Great Scientist" not in names
    assert "Great Artist" not in names


def test_no_water_units(constructions):
    names = _names(constructions)
    assert "Trireme" not in names
    assert "Galley" not in names


def test_total_count_reasonable(constructions):
    assert 10 <= len(constructions) <= 20
