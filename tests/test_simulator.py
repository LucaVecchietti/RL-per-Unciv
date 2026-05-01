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
            "gold": 50.0,
            "happiness": 9.0,
            "cities": [{
                "name": "Delhi",
                "population": {"population": 1, "storedFood": 0},
                "cityConstructions": {
                    "currentConstruction": "Monument",
                    "builtBuildings": [],
                    "productionAccumulated": 0,
                },
                "health": 200,
                "tiles": [],
            }],
            "tech": {
                "techsResearched": ["Agriculture"],
                "currentTechnology": "Pottery",
                "scienceAccumulated": 0,
            },
        }],
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
    pop["storedFood"] = 11  # +2/turn → 13 >= threshold(pop=1)=13
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
