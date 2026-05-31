import json
import gzip
import re
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# Building flags tracked in observation vector (alphabetical — matches ACTION_MAP order)
_TRACKED_BUILDINGS = [
    "Barracks", "Colosseum", "Courthouse", "Granary", "Library",
    "Monument", "Stable", "Temple", "Walls",
]

# Approximate science costs per tech (for progress normalization)
_TECH_COSTS: dict[str, float] = {
    'Agriculture': 20, 'Pottery': 35, 'Animal Husbandry': 35,
    'Mining': 35, 'Sailing': 55, 'Calendar': 55, 'Writing': 55,
    'Bronze Working': 55, 'Trapping': 55, 'The Wheel': 55,
    'Masonry': 80, 'Irrigation': 80, 'Mathematics': 100,
    'Construction': 100, 'Horseback Riding': 100, 'Philosophy': 100,
    'Iron Working': 150, 'Compass': 150, 'Optics': 150,
    'Currency': 250, 'Engineering': 250, 'Metal Casting': 250,
}

# Approximate production costs per construction
_CONSTRUCTION_COSTS: dict[str, float] = {
    'Monument': 60, 'Granary': 100, 'Library': 100, 'Barracks': 75,
    'Walls': 65, 'Market': 150, 'Courthouse': 200, 'Aqueduct': 100,
    'Settler': 106, 'Worker': 75, 'Warrior': 40, 'Scout': 25,
    'Archer': 40, 'Spearman': 56, 'Chariot Archer': 56,
}

# statsHistory è CivRankingHistory (punteggi di classifica, NON rese per turno).
# Lettere = RankingType.idForSerialization. Solo H/P/C sono usabili come valori utili qui.
_STATS_LETTERS = {
    'S': 'score', 'N': 'population', 'C': 'food_per_turn', 'P': 'production_per_turn',
    'G': 'gold_total', 'T': 'territory', 'F': 'force', 'H': 'happiness',
    'W': 'n_techs', 'A': 'n_policies',
}

# File 22 (C2) — raggio (in tile hex) per contare le risorse vicine all'unità selezionata
_RESOURCE_OBS_RADIUS = 3


def _hex_distance(x1: int, y1: int, x2: int, y2: int) -> int:
    """Distanza esagonale Unciv (senza world-wrap), coerente con HexMath.getDistance."""
    dx, dy = x1 - x2, y1 - y2
    if (dx >= 0) == (dy >= 0):
        return max(abs(dx), abs(dy))
    return abs(dx) + abs(dy)


@dataclass
class UnitState:
    """Stato di una singola unità militare o civile."""

    name: str
    x: int
    y: int
    movement_points: float
    health: int = 100
    id: int = -1


@dataclass
class CityState:
    """Stato di una singola città."""

    name: str
    population: int
    current_construction: str
    built_buildings: list[str]
    health: int
    tiles_count: int
    # Fase 2.0 — dati reali dal save JSON
    food_stored: float = 0.0
    food_threshold: float = 15.0
    food_per_turn: float = 0.0
    production_stored: float = 0.0
    current_construction_cost: float = 60.0
    production_per_turn: float = 0.0
    gold_per_turn: float = 0.0
    tiles_worked: int = 1
    x: int = 0
    y: int = 0
    # File 22 (C2) — risorse nel territorio
    territory_strategic: int = 0
    territory_luxury: int = 0
    # File 23.1 — risorse Bonus nel territorio (parallelo a strategic/luxury)
    territory_bonus: int = 0
    # Sessione 46 — coda di costruzione vuota: True se constructionQueue è vuota
    # oppure contiene solo "Nothing" (PerpetualConstruction.idle, cfr. IConstruction.kt:303).
    # Le altre perpetual (Science/Gold conversion) NON contano come empty perché sono
    # lavoro reale che il city manager sta facendo.
    construction_queue_empty: bool = True


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
    map_radius: int = 10
    # Fase 2.0
    units: list[UnitState] = field(default_factory=list)
    tiles_explored: int = 0
    total_tiles: int = 0
    science_per_turn: float = 0.0
    culture_per_turn: float = 0.0
    current_tech_progress: float = 0.0
    current_tech_cost: float = 60.0
    n_known_civs: int = 0
    at_war: bool = False
    gold_per_turn: float = 0.0
    # File 19 — extended metrics logging
    city_territory_tiles: int = 0
    strategic_resources: dict[str, int] = field(default_factory=dict)
    luxury_resources: dict[str, int] = field(default_factory=dict)
    # File 20 — cultura accumulata (per calcolo cultura/turno come delta in UncivEnv)
    stored_culture: float = 0.0
    # File 22 (C2) — posizioni risorse Strategic/Luxury: {(x, y): tipo}
    resource_tiles: dict = field(default_factory=dict)
    # File 22 (C3) — risorse connesse (nel territorio + miglioramento giusto costruito)
    connected_strategic: int = 0
    connected_luxury: int = 0
    # File 23.1 — risorse Bonus connesse (parallelo a strategic/luxury)
    connected_bonus: int = 0
    # File 22 (C3) — posizioni delle risorse già connesse (per maschera Improve mirata)
    resource_connected_tiles: set = field(default_factory=set)
    # File 23.1 — fede per turno (default 0; campo non direttamente nel save, eventualmente
    # calcolato a runtime come delta di religionManager.storedFaith analogamente a culture_per_turn).
    # TODO: parsing faith — il save espone solo civ.religionManager.storedFaith,
    # non c'è un faithPerTurn diretto: serve un meccanismo delta lato UncivEnv come per stored_culture.
    faith_per_turn: float = 0.0
    # Sessione 46 — set dei nomi città annesse (per masking building "Annexed only" come Courthouse).
    # TODO: il save Unciv non espone un flag esplicito "annessa" per le città auto-fondate;
    # i campi candidati (isPuppet, wasPreviouslyConquered, isOriginalCapital=false) non bastano
    # a distinguere annessa-da-conquista da fondata-poi-spostata-capitale. In Fase 2 (India senza
    # nemici) tutte le città sono auto-fondate quindi nessuna è annessa → set() è corretto.
    # Da rivedere quando entrerà il combattimento (Fase 3).
    annexed_cities: set = field(default_factory=set)


class UncivStateParser:
    """
    Legge un file di salvataggio Unciv (JSON o JSON.gz)
    e lo converte in strutture dati Python usabili dall'ambiente RL.
    """

    def __init__(
        self,
        player_civ: str = "India",
        resource_types: Optional[dict] = None,
        resource_improvements: Optional[dict] = None,
    ) -> None:
        self.player_civ = player_civ
        # Mappa nome risorsa → tipo (Strategic/Luxury/Bonus), dal ruleset JAR
        self.resource_types: dict = resource_types or {}
        # Mappa nome risorsa → miglioramento che la connette (es. Iron→Mine)
        self.resource_improvements: dict = resource_improvements or {}

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
        civ = self._find_player_civ(raw)
        cities = [self._parse_city(c) for c in civ.get('cities', [])]
        tech = civ.get('tech', {})

        # Tech corrente da techsInProgress (prima chiave)
        techs_researched: list[str] = tech.get('techsResearched', [])
        techs_in_progress: dict = tech.get('techsInProgress') or {}
        current_tech: Optional[str] = next(iter(techs_in_progress), None)
        current_tech_progress = float(techs_in_progress.get(current_tech, 0.0)) if current_tech else 0.0
        current_tech_cost = float(_TECH_COSTS.get(current_tech, 60.0)) if current_tech else 60.0

        # statsHistory = CivRankingHistory (vedi _STATS_LETTERS): NON sono rese per turno.
        # Solo H (Happiness), P (Production/turno) e C (Growth = cibo/turno) sono usabili.
        stats = self._parse_stats_history(civ)
        happiness = float(stats.get('H', 8))
        production_per_turn = float(stats.get('P', 0))
        food_per_turn = float(stats.get('C', 0))
        # Scienza/turno: sorgente autoritativa coerente con _advance_tech
        science_history = tech.get('scienceOfLast8Turns') or []
        science_per_turn = float(science_history[-1]) if science_history else 0.0
        # 'N' è la popolazione, non l'oro → gold/turno non disponibile qui (oro reale = civ.gold)
        gold_per_turn = 0.0
        # cultura/turno: calcolata in UncivEnv come delta di stored_culture (il parser non ha lo stato precedente)
        culture_per_turn = 0.0
        stored_culture = float(civ.get('policies', {}).get('storedCulture', 0) or 0)

        # Rese per-turno (stima civ-level) assegnate alla città principale (mono-città)
        if cities:
            cities[0].production_per_turn = production_per_turn
            cities[0].food_per_turn = food_per_turn

        # File 19 — territorio città e risorse
        city_territory_tiles = sum(len(c.get('tiles', [])) for c in civ.get('cities', []))
        strategic_resources: dict[str, int] = {}
        luxury_resources: dict[str, int] = {}
        for entry in civ.get('detailedCivResources', []) or []:
            res = entry.get('resource', {})
            name = res.get('name', '')
            amount = int(entry.get('amount', 0))
            rtype = res.get('resourceType', '')
            if rtype == 'Strategic':
                strategic_resources[name] = strategic_resources.get(name, 0) + amount
            elif rtype == 'Luxury':
                luxury_resources[name] = luxury_resources.get(name, 0) + amount

        # Mappa e unità
        tile_map = raw.get('tileMap', {})
        tile_list: list = tile_map.get('tileList', [])
        map_size = tile_map.get('mapParameters', {}).get('mapSize', {})
        map_width = int(map_size.get('width', 20))
        map_height = int(map_size.get('height', 20))
        map_radius = int(map_size.get('radius', 10))

        total_tiles = len(tile_list)
        tiles_explored = sum(
            1 for t in tile_list if self.player_civ in t.get('exploredBy', [])
        )
        units = self._parse_units(tile_list)

        # File 22 (C2/C3) — posizioni risorse Strategic/Luxury/Bonus (tipo dal ruleset)
        # e quali sono connesse (File 23.1 estende anche alle Bonus, che hanno tutte un improvement
        # connettore tipo Pasture/Camp/Farm/Quarry/Fishing Boats/Plantation).
        resource_tiles: dict[tuple[int, int], str] = {}
        resource_connected: set[tuple[int, int]] = set()
        for t in tile_list:
            res = t.get('resource')
            if not res:
                continue
            rtype = self.resource_types.get(res, '')
            if rtype not in ('Strategic', 'Luxury', 'Bonus'):
                continue
            pos = t.get('position', {})
            key = (int(pos.get('x', 0)), int(pos.get('y', 0)))
            resource_tiles[key] = rtype
            conn_imp = self.resource_improvements.get(res)
            if conn_imp and t.get('improvement') == conn_imp:
                resource_connected.add(key)

        # Conteggio risorse nel territorio di ogni città (totali e connesse)
        connected_strategic = connected_luxury = connected_bonus = 0
        for cr, cs in zip(civ.get('cities', []), cities):
            strat = lux = bonus_cnt = 0
            for tp in cr.get('tiles', []):
                if not isinstance(tp, dict):
                    continue
                key = (int(tp.get('x', 0)), int(tp.get('y', 0)))
                rt = resource_tiles.get(key)
                if rt == 'Strategic':
                    strat += 1
                    if key in resource_connected:
                        connected_strategic += 1
                elif rt == 'Luxury':
                    lux += 1
                    if key in resource_connected:
                        connected_luxury += 1
                elif rt == 'Bonus':
                    bonus_cnt += 1
                    if key in resource_connected:
                        connected_bonus += 1
            cs.territory_strategic = strat
            cs.territory_luxury = lux
            cs.territory_bonus = bonus_cnt

        # Diplomazia — at war se diplomaticStatus == 'War'
        diplomacy: dict = civ.get('diplomacy', {})
        at_war = any(
            isinstance(d, dict) and d.get('diplomaticStatus') == 'War'
            for d in diplomacy.values()
        )
        # n_known_civs da proximity (civs note dalla vicinanza)
        n_known_civs = len(civ.get('proximity', {}))

        return GameState(
            turn=raw.get('turns', 0),
            current_player=raw.get('currentPlayer', ''),
            gold=float(civ.get('gold', 0)),
            happiness=happiness,
            cities=cities,
            techs_researched=techs_researched,
            current_tech=current_tech,
            map_width=map_width,
            map_height=map_height,
            map_radius=map_radius,
            units=units,
            tiles_explored=tiles_explored,
            total_tiles=total_tiles,
            science_per_turn=science_per_turn,
            culture_per_turn=culture_per_turn,
            current_tech_progress=current_tech_progress,
            current_tech_cost=current_tech_cost,
            n_known_civs=n_known_civs,
            at_war=at_war,
            gold_per_turn=gold_per_turn,
            city_territory_tiles=city_territory_tiles,
            strategic_resources=strategic_resources,
            luxury_resources=luxury_resources,
            stored_culture=stored_culture,
            resource_tiles=resource_tiles,
            connected_strategic=connected_strategic,
            connected_luxury=connected_luxury,
            connected_bonus=connected_bonus,
            resource_connected_tiles=resource_connected,
            # File 23.1 — faith/turno non disponibile direttamente nel save: lasciato default 0.
            # TODO: parsing faith — religionManager.storedFaith è leggibile; per ottenere il delta
            # va memorizzato lo stato precedente in UncivEnv (come si fa già per stored_culture).
            faith_per_turn=0.0,
        )

    def _find_player_civ(self, raw: dict) -> dict:
        """Cerca e restituisce i dati della civilizzazione del player."""
        for civ in raw.get('civilizations', []):
            if civ.get('civName') == self.player_civ:
                return civ
        raise ValueError(f"Civilizzazione '{self.player_civ}' non trovata nel save file")

    def _parse_city(self, city_raw: dict) -> CityState:
        """Converte un dizionario città raw in CityState."""
        cc = city_raw.get('cityConstructions', {})

        # Popolazione — count non salvato se =1 (default Unciv), solo foodStored
        pop_data = city_raw.get('population', {})
        population = int(pop_data.get('population', 1))
        food_stored = float(pop_data.get('foodStored', 0))
        food_threshold = max(15.0 + population * 5.0, 1.0)

        # Costruzione corrente da constructionQueue
        queue: list = cc.get('constructionQueue', [])
        current_construction = queue[0] if queue else ''
        in_progress: dict = cc.get('inProgressConstructions', {})
        production_stored = float(in_progress.get(current_construction, 0))
        current_construction_cost = float(_CONSTRUCTION_COSTS.get(current_construction, 60.0))

        # Sessione 46 — coda vuota: nessun item OR solo "Nothing" (PerpetualConstruction.idle).
        # Le altre perpetual (Science/Gold conversion) sono lavoro reale → coda NON vuota.
        construction_queue_empty = (
            not queue
            or all(item == 'Nothing' for item in queue)
        )

        built: list[str] = cc.get('builtBuildings', [])
        tiles_worked = len(city_raw.get('workedTiles', []))
        tiles_count = len(city_raw.get('tiles', []))

        loc = city_raw.get('location', {})

        return CityState(
            name=city_raw.get('name', ''),
            population=population,
            current_construction=current_construction,
            built_buildings=built,
            health=city_raw.get('health', 200),
            tiles_count=tiles_count,
            food_stored=food_stored,
            food_threshold=food_threshold,
            food_per_turn=0.0,        # non nel JSON, calcolato a runtime
            production_stored=production_stored,
            current_construction_cost=current_construction_cost,
            production_per_turn=0.0,  # non nel JSON, calcolato a runtime
            gold_per_turn=0.0,        # non nel JSON
            tiles_worked=tiles_worked,
            x=int(loc.get('x', 0)),
            y=int(loc.get('y', 0)),
            construction_queue_empty=construction_queue_empty,
        )

    def _parse_units(self, tile_list: list) -> list[UnitState]:
        """Estrae le unità del player dalla tileList."""
        units: list[UnitState] = []
        for tile in tile_list:
            for slot in ('militaryUnit', 'civilianUnit'):
                u = tile.get(slot)
                if u and u.get('owner') == self.player_civ:
                    pos = tile.get('position', {})
                    units.append(UnitState(
                        name=u.get('name', ''),
                        x=int(pos.get('x', 0)),
                        y=int(pos.get('y', 0)),
                        movement_points=float(u.get('currentMovement', 0.0)),
                        health=int(u.get('health', 100)),
                        id=int(u.get('id', -1)),
                    ))
        return units

    def _parse_stats_history(self, civ: dict) -> dict[str, int]:
        """
        Parsa l'ultima voce di statsHistory nel formato 'S44N1C2P5G9T7F28H8W1A0'.
        Restituisce dict {lettera: intero} per i campi trovati.
        """
        history: dict = civ.get('statsHistory', {})
        if not history:
            return {}
        latest_turn = max(history.keys(), key=int)
        entry: str = history[latest_turn]
        return {m.group(1): int(m.group(2)) for m in re.finditer(r'([A-Z])(-?\d+)', entry)}

    def to_observation_vector(
        self,
        state: GameState,
        selected_unit: Optional[UnitState] = None,
        selected_city: Optional[CityState] = None,
    ) -> np.ndarray:
        """
        Converte GameState in vettore numpy (52,) float32.

        Layout:
          [0-5]   Globale: turn, gold, happiness, science/turn, culture/turn, n_cities
          [6-21]  Città 1: pop, food_prog, prod_prog, gold/t, food/t, prod/t,
                           n_buildings, has_monument…has_market, tiles_worked, x, y
          [22-29] Tech: n_techs, tech_progress, has_agriculture…has_animal_husbandry
          [30-37] Unità: n_warriors, n_settlers, n_other, warrior_xy, settler_xy, explored
          [38-45] Città 2 (zeros se assente)
          [46-47] Diplomazia: n_known_civs, at_war
          [48-51] Unità selezionata: sel_x, sel_y, sel_movement, tiles_explored_ratio
        """
        total = float(state.total_tiles) or 1.0
        r = float(state.map_radius) or 10.0

        def _norm_coord(v: float) -> float:
            # Coordinate hex centrate sull'origine (anche negative) → [0,1] via raggio mappa
            return float(np.clip((v / r + 1.0) / 2.0, 0.0, 1.0))

        obs: list[float] = []

        # --- Globale (6) ---
        obs += [
            np.clip(state.turn / 500.0, 0.0, 1.0),
            np.clip(state.gold / 1000.0, 0.0, 1.0),
            np.clip(state.happiness / 20.0, -1.0, 1.0),
            np.clip(state.science_per_turn / 50.0, 0.0, 1.0),
            np.clip(state.culture_per_turn / 20.0, 0.0, 1.0),
            np.clip(len(state.cities) / 10.0, 0.0, 1.0),
        ]

        # --- Città 1 (19) ---
        def _city_obs(c: CityState) -> list[float]:
            ft = max(c.food_threshold, 1.0)
            cc = max(c.current_construction_cost, 1.0)
            flags = [1.0 if b in c.built_buildings else 0.0 for b in _TRACKED_BUILDINGS]
            return (
                [
                    np.clip(c.population / 20.0, 0.0, 1.0),
                    np.clip(c.food_stored / ft, 0.0, 1.0),
                    np.clip(c.production_stored / cc, 0.0, 1.0),
                    np.clip(c.gold_per_turn / 20.0, 0.0, 1.0),
                    np.clip(c.food_per_turn / 20.0, 0.0, 1.0),
                    np.clip(c.production_per_turn / 20.0, 0.0, 1.0),
                    np.clip(len(c.built_buildings) / 20.0, 0.0, 1.0),
                ]
                + flags
                + [
                    np.clip(c.tiles_worked / 36.0, 0.0, 1.0),
                    _norm_coord(c.x),
                    _norm_coord(c.y),
                ]
            )

        # Città 1 = città selezionata (per-city rotation); fallback alla prima città
        city1 = selected_city if selected_city is not None else (state.cities[0] if state.cities else None)
        obs += _city_obs(city1) if city1 is not None else [0.0] * 19

        # --- Tech (8) ---
        tr = state.techs_researched
        tc = max(state.current_tech_cost, 1.0)
        obs += [
            np.clip(len(tr) / 80.0, 0.0, 1.0),
            np.clip(state.current_tech_progress / tc, 0.0, 1.0),
            float('Agriculture' in tr),
            float('Pottery' in tr),
            float('Writing' in tr),
            float('Mining' in tr),
            float('Bronze Working' in tr),
            float('Animal Husbandry' in tr),
        ]

        # --- Unità (8) ---
        warriors = [u for u in state.units if u.name == 'Warrior']
        settlers = [u for u in state.units if u.name == 'Settler']
        other = [u for u in state.units if u.name not in ('Warrior', 'Settler')]
        wp = warriors[0] if warriors else None
        sp = settlers[0] if settlers else None
        obs += [
            np.clip(len(warriors) / 10.0, 0.0, 1.0),
            np.clip(len(settlers) / 5.0, 0.0, 1.0),
            np.clip(len(other) / 10.0, 0.0, 1.0),
            _norm_coord(wp.x) if wp else 0.0,
            _norm_coord(wp.y) if wp else 0.0,
            _norm_coord(sp.x) if sp else 0.0,
            _norm_coord(sp.y) if sp else 0.0,
            np.clip(state.tiles_explored / total, 0.0, 1.0),
        ]

        # --- Città 2 (10) — struttura città 1 senza building flags ---
        if len(state.cities) >= 2:
            c2 = state.cities[1]
            ft2 = max(c2.food_threshold, 1.0)
            cc2 = max(c2.current_construction_cost, 1.0)
            obs += [
                np.clip(c2.population / 20.0, 0.0, 1.0),
                np.clip(c2.food_stored / ft2, 0.0, 1.0),
                np.clip(c2.production_stored / cc2, 0.0, 1.0),
                np.clip(c2.gold_per_turn / 20.0, 0.0, 1.0),
                np.clip(c2.food_per_turn / 20.0, 0.0, 1.0),
                np.clip(c2.production_per_turn / 20.0, 0.0, 1.0),
                np.clip(len(c2.built_buildings) / 20.0, 0.0, 1.0),
                np.clip(c2.tiles_worked / 36.0, 0.0, 1.0),
                _norm_coord(c2.x),
                _norm_coord(c2.y),
            ]
        else:
            obs += [0.0] * 10

        # --- Diplomazia (2) ---
        obs += [
            np.clip(state.n_known_civs / 10.0, 0.0, 1.0),
            float(state.at_war),
        ]

        # --- Unità selezionata (4) — usata da per-entity rotation in Fase 2.1 ---
        obs += [
            _norm_coord(selected_unit.x) if selected_unit else 0.0,
            _norm_coord(selected_unit.y) if selected_unit else 0.0,
            np.clip(selected_unit.movement_points / 2.0, 0.0, 1.0) if selected_unit else 0.0,
            np.clip(state.tiles_explored / total, 0.0, 1.0),
        ]

        # --- Risorse (4) — File 22 C2 ---
        sc = selected_city if selected_city is not None else (state.cities[0] if state.cities else None)

        def _nearby_res(u: Optional[UnitState], rtype: str) -> int:
            if u is None:
                return 0
            return sum(
                1 for (rx, ry), t in state.resource_tiles.items()
                if t == rtype and _hex_distance(u.x, u.y, rx, ry) <= _RESOURCE_OBS_RADIUS
            )

        obs += [
            np.clip((sc.territory_strategic if sc else 0) / 10.0, 0.0, 1.0),
            np.clip((sc.territory_luxury if sc else 0) / 10.0, 0.0, 1.0),
            np.clip(_nearby_res(selected_unit, 'Strategic') / 10.0, 0.0, 1.0),
            np.clip(_nearby_res(selected_unit, 'Luxury') / 10.0, 0.0, 1.0),
        ]

        result = np.array(obs, dtype=np.float32)
        assert result.shape == (61,), f"Expected (61,), got {result.shape}"
        return result
