"""Reads Buildings, Units, Techs from Unciv JAR and filters early-game constructions."""

import json
import re
import zipfile
from dataclasses import dataclass
from typing import Optional


@dataclass
class ConstructionInfo:
    """A buildable construction (building or unit) available in early-game eras."""

    name: str
    required_tech: Optional[str]
    is_unit: bool


_BUILDINGS_PATH = "jsons/Civ V - Vanilla/Buildings.json"
_UNITS_PATH = "jsons/Civ V - Vanilla/Units.json"
_TECHS_PATH = "jsons/Civ V - Vanilla/Techs.json"
_RESOURCES_PATH = "jsons/Civ V - Vanilla/TileResources.json"

_TARGET_ERAS = {"Ancient", "Classical", "Ancient era", "Classical era"}

_BUILDING_EXCLUDE = {
    "Krepost", "Burial Tomb", "Mud Pyramid Mosque", "Paper Maker",
    "Floating Gardens", "Stone Works", "Water Mill", "Circus", "Longhouse",
    "Lighthouse",  # coastal-only, not universally useful early game
}

_UNIT_EXCLUDE = {"Maori Warrior", "Jaguar", "Brute"}

_UNIT_MISC_EXCLUDE = {
    "Khan", "SS Booster", "SS Cockpit", "SS Engine", "SS Stasis Chamber",
    "Swordsman",  # Classical upgrade excluded to keep action space at 19
}

_ALLOWED_UNIT_TYPES = {"Sword", "Scout", "Civilian"}


def _load_jsonc(jar: zipfile.ZipFile, path: str) -> list:
    """Read JSONC from JAR: strip // and /* */ comments and trailing commas."""
    raw = jar.read(path).decode("utf-8")
    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
    raw = re.sub(r"//[^\n]*", "", raw)
    raw = re.sub(r",(\s*[}\]])", r"\1", raw)
    return json.loads(raw)


def get_ancient_classical_techs(jar_path: str) -> set[str]:
    """Return names of all Ancient + Classical era techs from the JAR."""
    with zipfile.ZipFile(jar_path, "r") as jar:
        techs = _load_jsonc(jar, _TECHS_PATH)
    result: set[str] = set()
    for era_block in techs:
        if era_block.get("era") not in _TARGET_ERAS:
            continue
        for tech in era_block.get("techs", []):
            result.add(tech["name"])
    return result


def load_tech_prereqs(jar_path: str) -> dict[str, list[str]]:
    """Return {tech_name: [prerequisite_tech_names]} for Ancient+Classical techs."""
    with zipfile.ZipFile(jar_path, "r") as jar:
        techs_data = _load_jsonc(jar, _TECHS_PATH)
    result: dict[str, list[str]] = {}
    for era_block in techs_data:
        if era_block.get("era") not in _TARGET_ERAS:
            continue
        for tech in era_block.get("techs", []):
            name = tech.get("name", "")
            result[name] = tech.get("prerequisites", [])
    return result


def load_resource_types(jar_path: str) -> dict[str, str]:
    """Return {resource_name: resourceType} (Strategic/Luxury/Bonus) from TileResources.json."""
    with zipfile.ZipFile(jar_path, "r") as jar:
        data = _load_jsonc(jar, _RESOURCES_PATH)
    result: dict[str, str] = {}
    for r in data:
        name = r.get("name", "")
        if name:
            result[name] = r.get("resourceType", "")
    return result


def load_early_game_constructions(jar_path: str) -> list[ConstructionInfo]:
    """
    Read buildings + units from the Unciv JAR, return Ancient + Classical constructions.

    Excludes wonders, national wonders, civ-unique, aquatic units, Great People.
    Order: buildings alphabetical, then units alphabetical.
    """
    ac_techs = get_ancient_classical_techs(jar_path)

    with zipfile.ZipFile(jar_path, "r") as jar:
        buildings_data = _load_jsonc(jar, _BUILDINGS_PATH)
        units_data = _load_jsonc(jar, _UNITS_PATH)

    buildings: list[ConstructionInfo] = []
    for b in buildings_data:
        name = b.get("name", "")
        if name in _BUILDING_EXCLUDE:
            continue
        if b.get("isWonder", False) or b.get("isNationalWonder", False):
            continue
        if b.get("uniqueTo"):
            continue
        req_tech = b.get("requiredTech")
        if req_tech is not None and req_tech not in ac_techs:
            continue
        buildings.append(ConstructionInfo(name=name, required_tech=req_tech, is_unit=False))
    buildings.sort(key=lambda c: c.name)

    units: list[ConstructionInfo] = []
    for u in units_data:
        name = u.get("name", "")
        if name in _UNIT_EXCLUDE or name in _UNIT_MISC_EXCLUDE:
            continue
        if name.startswith("Great "):
            continue
        if u.get("uniqueTo"):
            continue
        if u.get("unitType", "") not in _ALLOWED_UNIT_TYPES:
            continue
        req_tech = u.get("requiredTech")
        if req_tech is not None and req_tech not in ac_techs:
            continue
        units.append(ConstructionInfo(name=name, required_tech=req_tech, is_unit=True))
    units.sort(key=lambda c: c.name)

    return buildings + units
