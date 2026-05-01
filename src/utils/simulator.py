"""
Micro-simulatore Python per Unciv — Fase 1.5.
Sostituito da UncivHeadless (src/utils/headless.py) nella Fase 2 (file 08).
"""
from __future__ import annotations
from typing import Optional


CONSTRUCTION_COSTS: dict[str, int] = {
    "Monument": 60,
    "Granary": 60,
    "Library": 90,
    "Barracks": 70,
    "Settler": 106,
    "Warrior": 40,
}

TECH_COSTS: dict[str, int] = {
    "Agriculture": 20,
    "Mining": 35,
    "Writing": 55,
    "Pottery": 35,
    "Animal Husbandry": 35,
    "Archery": 35,
    "Bronze Working": 55,
    "Sailing": 55,
    "Trapping": 55,
    "The Wheel": 55,
    "Masonry": 55,
    "Calendar": 70,
    "Mathematics": 100,
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
