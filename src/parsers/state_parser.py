import json
import gzip
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CityState:
    """Stato di una singola città."""

    name: str
    population: int
    current_construction: str
    built_buildings: list[str]
    health: int
    tiles_count: int


@dataclass
class GameState:
    """Stato completo del gioco estratto dal save file Unciv."""

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

    def __init__(self, player_civ: str = "Romans") -> None:
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
        """Estrae GameState dal dizionario JSON grezzo."""
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
        """Cerca e restituisce i dati della civilizzazione del player."""
        for civ in raw.get("civilizations", []):
            if civ.get("civName") == self.player_civ:
                return civ
        raise ValueError(f"Civilizzazione '{self.player_civ}' non trovata nel save file")

    def _parse_city(self, city_raw: dict) -> CityState:
        """Converte un dizionario città raw in CityState."""
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

        Fase 1 — vettore di dimensione (7,) float32:
          [0] turn / 500
          [1] gold / 1000
          [2] happiness / 20
          [3] num_cities / 10
          [4] num_techs / 80
          [5] first_city_population / 20
          [6] first_city_built_buildings / 20
        """
        obs = [
            state.turn / 500.0,
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
