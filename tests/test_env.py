import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from src.envs.unciv_env import UncivEnv
from src.parsers.state_parser import GameState, CityState, UnitState


def _make_config(tmp_path: object) -> str:
    import yaml
    config = {
        "training": {"total_timesteps": 1000},
        "environment": {"max_turns": 50, "map_size": "tiny", "victory_type": "science"},
        "paths": {
            "save_dir": str(tmp_path / "models"),
            "log_dir": str(tmp_path / "logs"),
            "unciv_saves": str(tmp_path / "saves"),
        },
    }
    config_path = tmp_path / "config.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(config, f)
    return str(config_path)


@pytest.fixture
def env(tmp_path):
    return UncivEnv(config_path=_make_config(tmp_path), env_rank=0)


def _mock_state(units: list[UnitState] | None = None) -> GameState:
    return GameState(
        10, "India", 200, 5,
        [CityState("Rome", 3, "Monument", [], 200, 0)],
        ["Agriculture"], "Writing", 20, 20,
        units=units or [],
    )


def _get_idx(env: UncivEnv, name) -> int:
    """Lookup action index by name in env.ACTION_MAP."""
    return next(i for i, n in env.ACTION_MAP.items() if n == name)


def test_spaces(env):
    # File 24 — action space cresce di +1 (BUILD_ROAD), obs di +3 (trade-network).
    assert env.observation_space.shape == (64,)
    assert env.action_space.n == 24


def test_env_rank_uses_separate_save_files(tmp_path):
    """Due env con rank diversi devono usare save file separati."""
    cfg = _make_config(tmp_path)
    env0 = UncivEnv(config_path=cfg, env_rank=0)
    env1 = UncivEnv(config_path=cfg, env_rank=1)
    assert env0.save_path != env1.save_path
    assert "current_game_0" in str(env0.save_path)
    assert "current_game_1" in str(env1.save_path)


def test_step_output_shape(env):
    with patch.object(env, '_start_new_game'), \
         patch.object(env, '_apply_action'), \
         patch.object(env, '_advance_turn'), \
         patch.object(env.parser, 'parse') as mock_parse:
        mock_state = _mock_state()
        mock_parse.return_value = mock_state
        env._current_state = mock_state
        obs, reward, term, trunc, info = env.step(0)
        # File 24 — obs shape passa a (64,).
        assert obs.shape == (64,)
        assert isinstance(reward, float)
        assert isinstance(term, bool)


def _setup_masking(env: UncivEnv, techs_researched=None, built_buildings=None) -> None:
    """Set deterministic prereq_map + ACTION_MAP + state for masking tests."""
    env._prereq_map = {
        "Monument": None, "Granary": "Pottery", "Library": "Writing",
        "Barracks": "Bronze Working", "Settler": None, "Warrior": None,
    }
    env._building_names = {"Monument", "Granary", "Library", "Barracks"}
    env._unit_names = {"Settler", "Warrior"}
    buildings = sorted(env._building_names)   # Barracks, Granary, Library, Monument
    units = sorted(env._unit_names)            # Settler, Warrior
    action_list = buildings + units + [None] + ["MOVE_NORTH", "MOVE_SOUTH", "MOVE_EAST", "MOVE_WEST"]
    env.ACTION_MAP = {i: n for i, n in enumerate(action_list)}
    env._skip_idx = action_list.index(None)
    env._move_start_idx = env._skip_idx + 1
    env._current_state = GameState(
        10, "India", 200, 5,
        [CityState("Delhi", 3, "Monument", built_buildings or [], 200, 0)],
        techs_researched or [], "Writing", 20, 20,
    )
    env._step_type = "city"


def test_action_masks_city_step(env):
    _setup_masking(env, techs_researched=["Pottery", "Writing", "Bronze Working"])
    masks = env.action_masks()
    assert masks.shape == (11,)
    assert masks.dtype == bool
    # Building+unit disponibili (indici 0..5: 4 buildings + 2 units).
    assert all(masks[0:6])
    # Skip (indice 6): Sessione 46 Fix #3 — mascherato se coda vuota E alternative.
    # CityState.construction_queue_empty default True → skip masked.
    assert not masks[6]
    # MOVE non disponibili in city step.
    assert not any(masks[7:11])


def test_action_masks_unit_step(env):
    """Unit step: solo skip + le direzioni hex legali (da headless.legal_moves)."""
    warrior = UnitState("Warrior", x=0, y=0, movement_points=2.0, id=5)
    env._step_type = "unit"
    env._pending_units = [warrior]
    env._unit_rotation_index = 0
    env._current_state = _mock_state(units=[warrior])
    with patch.object(env.headless, "legal_moves", return_value=[2, 6]):
        masks = env.action_masks()
    skip = env._skip_idx
    assert masks.shape == (len(env.ACTION_MAP),)
    assert masks[skip]
    assert not any(masks[:skip])  # niente costruzioni in unit step
    clock2 = next(i for i, c in env._action_to_clock.items() if c == 2)
    clock4 = next(i for i, c in env._action_to_clock.items() if c == 4)
    clock6 = next(i for i, c in env._action_to_clock.items() if c == 6)
    assert masks[clock2] and masks[clock6]
    assert not masks[clock4]


def test_mask_monument_available_when_not_built(env):
    _setup_masking(env, built_buildings=[])
    assert env.action_masks()[_get_idx(env, "Monument")]


def test_mask_monument_blocked_when_already_built(env):
    _setup_masking(env, built_buildings=["Monument"])
    assert not env.action_masks()[_get_idx(env, "Monument")]


def test_mask_library_blocked_without_writing(env):
    _setup_masking(env, techs_researched=[])
    assert not env.action_masks()[_get_idx(env, "Library")]


def test_mask_library_available_with_writing(env):
    _setup_masking(env, techs_researched=["Writing"])
    assert env.action_masks()[_get_idx(env, "Library")]


def test_mask_skip_available_when_queue_not_empty_city_step(env):
    """Sessione 46 Fix #3: skip disponibile se la coda di costruzione non è vuota."""
    _setup_masking(env, techs_researched=[], built_buildings=["Monument"])
    env._current_state.cities[0].construction_queue_empty = False
    assert env.action_masks()[env._skip_idx]


def test_mask_skip_masked_when_queue_empty_and_alternatives(env):
    """Sessione 46 Fix #3: skip mascherato se coda vuota E ci sono alternative valide."""
    _setup_masking(env, techs_researched=["Pottery", "Writing"], built_buildings=[])
    env._current_state.cities[0].construction_queue_empty = True
    assert not env.action_masks()[env._skip_idx]


def test_mask_skip_available_when_queue_empty_no_alternatives(env):
    """Sessione 46 Fix #3: fallback — skip resta disponibile se nessun building/unit valido."""
    # Tutti i building già built + tech vuoto + nessuna unit producibile.
    _setup_masking(
        env, techs_researched=[],
        built_buildings=["Monument", "Granary", "Library", "Barracks"],
    )
    env._current_state.cities[0].construction_queue_empty = True
    # Settler/Warrior potrebbero essere ancora disponibili (no tech req in mock);
    # questo test verifica che IL FALLBACK funzioni: se NESSUN building/unit valido,
    # skip resta True. Per garantire no alternative, sbianchiamo unit_names.
    env._unit_names = set()
    env.ACTION_MAP = {
        i: n for i, n in enumerate(
            sorted(env._building_names) + [None] + ["MOVE_NORTH", "MOVE_SOUTH"]
        )
    }
    env._skip_idx = next(i for i, n in env.ACTION_MAP.items() if n is None)
    env._move_start_idx = env._skip_idx + 1
    assert env.action_masks()[env._skip_idx]


def test_mask_move_false_in_city_step(env):
    _setup_masking(env)
    assert not any(env.action_masks()[env._move_start_idx:env._move_start_idx + 4])


def test_at_least_one_true_city_step(env):
    _setup_masking(
        env, techs_researched=[],
        built_buildings=["Monument", "Granary", "Library", "Barracks"],
    )
    assert env.action_masks().any()


def test_unit_step_only_skip_when_no_legal_moves(env):
    """Unità senza mosse legali → solo skip valido (anti-deadlock)."""
    warrior = UnitState("Warrior", x=0, y=0, movement_points=2.0, id=5)
    env._step_type = "unit"
    env._pending_units = [warrior]
    env._unit_rotation_index = 0
    env._current_state = _mock_state(units=[warrior])
    with patch.object(env.headless, "legal_moves", return_value=[]):
        masks = env.action_masks()
    assert masks[env._skip_idx]
    assert masks.sum() == 1


def test_per_entity_rotation_transitions_to_unit_step(env):
    """City step con warriors disponibili → torna obs senza avanzare turno."""
    warrior = UnitState("Warrior", x=5, y=5, movement_points=2.0)
    mock_state = _mock_state(units=[warrior])

    with patch.object(env, '_start_new_game'), \
         patch.object(env, '_apply_action'), \
         patch.object(env, '_advance_turn') as mock_adv, \
         patch.object(env.parser, 'parse', return_value=mock_state):
        env._current_state = mock_state
        obs, reward, term, trunc, info = env.step(0)

    # File 24 — obs shape passa a (64,).
    assert obs.shape == (64,)
    assert reward == 0.0
    assert term is False
    assert trunc is False
    assert env._step_type == "unit"
    mock_adv.assert_not_called()


def test_per_entity_rotation_advances_turn_after_warrior(env):
    """Unit step con un solo warrior → avanza turno."""
    warrior = UnitState("Warrior", x=5, y=5, movement_points=2.0)
    mock_state = _mock_state(units=[warrior])

    with patch.object(env, '_apply_action'), \
         patch.object(env, '_apply_movement'), \
         patch.object(env, '_advance_turn') as mock_adv, \
         patch.object(env, '_advance_tech'), \
         patch.object(env.parser, 'parse', return_value=mock_state):
        env._current_state = mock_state
        env._step_type = "unit"
        env._unit_rotation_index = 0
        env._pending_units = [warrior]
        env._buffered_city_action = env._skip_idx
        obs, reward, term, trunc, info = env.step(env._skip_idx)

    # File 24 — obs shape passa a (64,).
    assert obs.shape == (64,)
    assert env._step_type == "city"
    mock_adv.assert_called_once()


def test_advance_tech_accumulates_science(env, tmp_path):
    """_advance_tech accumula scienza in techsInProgress dalla history."""
    import json as _json
    save = tmp_path / "game.json"
    raw = {
        "civilizations": [{
            "civName": "India",
            "tech": {
                "techsResearched": ["Agriculture"],
                "techsInProgress": None,
                "scienceOfLast8Turns": [10],
            }
        }]
    }
    save.write_text(_json.dumps(raw))
    env.save_path = save
    env._tech_prereqs = {"Agriculture": [], "Mining": ["Agriculture"], "Pottery": ["Agriculture"]}
    env._advance_tech()
    result = _json.loads(save.read_text())
    tech = result["civilizations"][0]["tech"]
    assert tech["techsInProgress"] is not None
    chosen = next(iter(tech["techsInProgress"]))
    assert chosen in {"Mining", "Pottery"}
    assert tech["techsInProgress"][chosen] == 10.0


def test_advance_tech_completes_tech(env, tmp_path):
    """_advance_tech completa tech e avvia prossima con overflow."""
    import json as _json
    save = tmp_path / "game.json"
    # Pottery costs 35, in_progress=30, science=10 → completes with 5 overflow
    raw = {
        "civilizations": [{
            "civName": "India",
            "tech": {
                "techsResearched": ["Agriculture"],
                "techsInProgress": {"Pottery": 30.0},
                "scienceOfLast8Turns": [10],
            }
        }]
    }
    save.write_text(_json.dumps(raw))
    env.save_path = save
    env._tech_prereqs = {
        "Agriculture": [], "Pottery": ["Agriculture"], "Writing": ["Pottery"],
    }
    env._advance_tech()
    result = _json.loads(save.read_text())
    tech = result["civilizations"][0]["tech"]
    assert "Pottery" in tech["techsResearched"]
    # Writing unlocked after Pottery — should start with 5 overflow
    assert tech["techsInProgress"] == {"Writing": 5.0}


def test_obs_contains_selected_unit_coords(env):
    """In unit step, obs[53-55] riflettono unità selezionata (coord hex radius-based)."""
    warrior = UnitState("Warrior", x=0, y=0, movement_points=2.0, id=3)
    mock_state = _mock_state(units=[warrior])
    env._current_state = mock_state
    env._step_type = "unit"
    env._unit_rotation_index = 0
    env._pending_units = [warrior]

    obs = env._get_obs()
    # File 24 — obs shape passa a (64,).
    assert obs.shape == (64,)
    # x=0,y=0 con radius 10 → (0/10+1)/2 = 0.5 ; movement=2/2=1.0
    assert abs(obs[53] - 0.5) < 1e-5
    assert abs(obs[54] - 0.5) < 1e-5
    assert abs(obs[55] - 1.0) < 1e-5


# --- File 19 — extended metrics logging ---

def test_ep_buildings_built_tracks_new_construction(env):
    """turno N: built=[], turno N+1: built=[Monument] → ep_buildings_built == {Monument: 1}."""
    prev = _mock_state()  # città con built_buildings=[]
    curr = GameState(
        11, "India", 200, 5,
        [CityState("Rome", 3, "Monument", ["Monument"], 200, 0)],
        ["Agriculture"], "Writing", 20, 20, units=[],
    )
    env._current_state = prev
    env._ep_buildings_built = {}
    with patch.object(env, '_advance_turn'), \
         patch.object(env, '_advance_tech'), \
         patch.object(env.parser, 'parse', return_value=curr):
        env._advance_game_turn()
    assert env._ep_buildings_built == {"Monument": 1}


def test_ep_units_built_tracks_new_unit(env):
    """turno N: units=[], turno N+1: units=[Warrior] → ep_units_built == {Warrior: 1}."""
    prev = _mock_state(units=[])
    curr = _mock_state(units=[UnitState("Warrior", 5, 5, 2.0)])
    env._current_state = prev
    env._ep_units_built = {}
    with patch.object(env, '_advance_turn'), \
         patch.object(env, '_advance_tech'), \
         patch.object(env.parser, 'parse', return_value=curr):
        env._advance_game_turn()
    assert env._ep_units_built == {"Warrior": 1}


def test_ep_totals_reset_on_episode_reset(env):
    """Dopo reset() i contatori per-episodio tornano a zero/vuoto."""
    env._ep_total_gold = 99.0
    env._ep_buildings_built = {"Monument": 3}
    env._ep_units_built = {"Warrior": 2}
    with patch.object(env, '_start_new_game'), \
         patch.object(env.parser, 'parse', return_value=_mock_state()):
        env.reset()
    assert env._ep_total_gold == 0.0
    assert env._ep_buildings_built == {}
    assert env._ep_units_built == {}


def test_info_contains_new_metrics(env):
    """info dict da _advance_game_turn contiene tutte le nuove chiavi File 19."""
    curr = _mock_state()
    env._current_state = curr
    with patch.object(env, '_advance_turn'), \
         patch.object(env, '_advance_tech'), \
         patch.object(env.parser, 'parse', return_value=curr):
        obs, reward, term, trunc, info = env._advance_game_turn()
    for key in [
        "tiles_explored", "city_territory_tiles", "science_per_turn",
        "culture_per_turn", "strategic_resources", "luxury_resources",
        "ep_total_gold", "ep_total_science", "ep_total_culture",
        "ep_buildings_built", "ep_units_built",
    ]:
        assert key in info


# --- File 22 (C1) — espansione multi-città ---

def _multi_city_state(units=None):
    return GameState(
        10, "India", 200, 5,
        [CityState("Rome", 3, "Monument", [], 200, 0),
         CityState("Delhi", 9, "", ["Granary", "Library"], 200, 0)],
        ["Agriculture"], "Writing", 20, 20, units=units or [],
    )


def test_city_rotation_multiple_cities(env):
    """Con 2 città il city step si ripete per ogni città prima della fase unità/advance."""
    s = _multi_city_state()
    env._current_state = s
    env._pending_cities = list(s.cities)
    env._city_rotation_index = 0
    env._step_type = "city"
    with patch.object(env, '_apply_action'):
        obs, reward, term, trunc, info = env.step(0)
    assert env._step_type == "city"
    assert env._city_rotation_index == 1
    assert info.get("step_type") == "city"


def test_obs_reflects_selected_city(env):
    """L'obs (blocco Città1) riflette la città selezionata nella rotation."""
    s = _multi_city_state()
    env._current_state = s
    env._step_type = "city"
    env._pending_cities = list(s.cities)
    env._city_rotation_index = 1  # Delhi (pop 9)
    obs = env._get_obs()
    assert abs(obs[6] - 9 / 20.0) < 1e-5  # obs[6] = pop città selezionata / 20


def test_found_city_mask_for_settler(env):
    """FoundCity valido in unit step solo per i Settler."""
    settler = UnitState("Settler", x=0, y=0, movement_points=2.0, id=9)
    env._step_type = "unit"
    env._pending_units = [settler]
    env._unit_rotation_index = 0
    env._current_state = _mock_state(units=[settler])
    with patch.object(env.headless, "legal_moves", return_value=[]):
        masks = env.action_masks()
    assert masks[env._found_city_idx]


def test_apply_found_city_increments_counter(env):
    settler = UnitState("Settler", x=0, y=0, movement_points=2.0, id=9)
    env._ep_cities_founded = 0
    with patch.object(env.headless, "found_city",
                      return_value={"success": True, "x": 1, "y": 1}) as mock_found:
        env._apply_found_city(settler)
    mock_found.assert_called_once()
    assert env._ep_cities_founded == 1


# --- File 22 (C3) — miglioramenti Worker ---

def test_improve_mask_for_worker_on_resource(env):
    """Improve valido in unit step per un Worker SOLO se è su un tile-risorsa."""
    worker = UnitState("Worker", x=0, y=0, movement_points=2.0, id=12)
    state = _mock_state(units=[worker])
    state.resource_tiles = {(0, 0): "Strategic"}
    env._step_type = "unit"
    env._pending_units = [worker]
    env._unit_rotation_index = 0
    env._current_state = state
    with patch.object(env.headless, "legal_moves", return_value=[]):
        masks = env.action_masks()
    assert masks[env._improve_idx]
    assert not masks[env._found_city_idx]  # un Worker non fonda città


def test_improve_mask_off_when_worker_not_on_resource(env):
    """Senza risorsa sul tile, Improve non è valido (evita no-op/crash)."""
    worker = UnitState("Worker", x=5, y=5, movement_points=2.0, id=12)
    state = _mock_state(units=[worker])  # resource_tiles vuoto
    env._step_type = "unit"
    env._pending_units = [worker]
    env._unit_rotation_index = 0
    env._current_state = state
    with patch.object(env.headless, "legal_moves", return_value=[]):
        masks = env.action_masks()
    assert not masks[env._improve_idx]


def test_improve_mask_off_when_resource_already_connected(env):
    """Risorsa già connessa (miglioramento già costruito) → Improve NON valido (no retry inutili)."""
    worker = UnitState("Worker", x=0, y=0, movement_points=2.0, id=12)
    state = _mock_state(units=[worker])
    state.resource_tiles = {(0, 0): "Strategic"}
    state.resource_connected_tiles = {(0, 0)}  # già connessa
    env._step_type = "unit"
    env._pending_units = [worker]
    env._unit_rotation_index = 0
    env._current_state = state
    with patch.object(env.headless, "legal_moves", return_value=[]):
        masks = env.action_masks()
    assert not masks[env._improve_idx]


def test_apply_improve_increments_counter(env):
    worker = UnitState("Worker", x=0, y=0, movement_points=2.0, id=12)
    env._ep_improvements_built = 0
    with patch.object(env.headless, "build_improvement",
                      return_value={"success": True, "improvement": "Mine", "turns": 5}) as m:
        env._apply_improve(worker)
    m.assert_called_once()
    assert env._ep_improvements_built == 1


# --- File 20 — fix costruzione ---

# --- File 23.1 — units_stuck esposto per il reward shaping --------------------

def test_units_stuck_in_info_dict(env):
    """Dopo un game turn, info["units_stuck"] riflette il contatore _ep_units_stuck.

    File 23.1 introduce units_stuck_penalty (peso 0.02): la penalty richiede che il
    numero di unità stuck sia esposto. Attualmente l'env lo passa via info dict; il
    reward può consumarlo da lì o, in alternativa, da curr.units_stuck.
    """
    curr = _mock_state()
    env._current_state = curr
    env._ep_units_stuck = 7
    with patch.object(env, '_advance_turn'), \
         patch.object(env, '_advance_tech'), \
         patch.object(env.parser, 'parse', return_value=curr):
        obs, reward, term, trunc, info = env._advance_game_turn()
    assert "units_stuck" in info
    assert info["units_stuck"] == 7


def test_apply_action_sets_construction_queue(env, tmp_path):
    """_apply_action scrive constructionQueue[0], non il campo inesistente currentConstruction."""
    import json as _json
    save = tmp_path / "game.json"
    raw = {"civilizations": [{
        "civName": "India",
        "cities": [{"cityConstructions": {"currentConstruction": "Granary"}}],
    }]}
    save.write_text(_json.dumps(raw))
    env.save_path = save
    idx = _get_idx(env, "Monument")
    env._apply_action(idx)
    cc = _json.loads(save.read_text())["civilizations"][0]["cities"][0]["cityConstructions"]
    assert cc["constructionQueue"] == ["Monument"]
    assert cc["currentConstructionIsUserSet"] is True
    assert "inProgressConstructions" in cc
    assert "currentConstruction" not in cc


# --- File 24 — BUILD_ROAD action space + masking + step -----------------------


def test_action_space_size_24(env):
    """File 24 — action space cresce da 23 a 24 con l'aggiunta di BUILD_ROAD."""
    assert env.action_space.n == 24
    # L'indice BUILD_ROAD deve essere registrato e mappato sull'ACTION_MAP.
    assert env.ACTION_MAP[env._build_road_idx] == "BUILD_ROAD"


def test_build_road_masking_only_worker_no_road(env):
    """Worker su tile senza road → mask BUILD_ROAD = True."""
    worker = UnitState("Worker", x=0, y=0, movement_points=2.0, id=12)
    state = _mock_state(units=[worker])
    state.tiles_with_road = set()  # nessuna road
    env._step_type = "unit"
    env._pending_units = [worker]
    env._unit_rotation_index = 0
    env._current_state = state
    with patch.object(env.headless, "legal_moves", return_value=[]):
        masks = env.action_masks()
    assert masks[env._build_road_idx]


def test_build_road_masking_off_if_road_present(env):
    """Worker su tile in tiles_with_road → mask BUILD_ROAD = False (no doppia road)."""
    worker = UnitState("Worker", x=4, y=2, movement_points=2.0, id=12)
    state = _mock_state(units=[worker])
    state.tiles_with_road = {(4, 2)}  # road già presente sul tile del Worker
    env._step_type = "unit"
    env._pending_units = [worker]
    env._unit_rotation_index = 0
    env._current_state = state
    with patch.object(env.headless, "legal_moves", return_value=[]):
        masks = env.action_masks()
    assert not masks[env._build_road_idx]


def test_build_road_masking_off_for_non_worker(env):
    """Unità non-Worker (Settler / Warrior) → mask BUILD_ROAD = False."""
    settler = UnitState("Settler", x=0, y=0, movement_points=2.0, id=9)
    state = _mock_state(units=[settler])
    state.tiles_with_road = set()
    env._step_type = "unit"
    env._pending_units = [settler]
    env._unit_rotation_index = 0
    env._current_state = state
    with patch.object(env.headless, "legal_moves", return_value=[]):
        masks_settler = env.action_masks()
    assert not masks_settler[env._build_road_idx]

    warrior = UnitState("Warrior", x=0, y=0, movement_points=2.0, id=10)
    state2 = _mock_state(units=[warrior])
    state2.tiles_with_road = set()
    env._pending_units = [warrior]
    env._unit_rotation_index = 0
    env._current_state = state2
    with patch.object(env.headless, "legal_moves", return_value=[]):
        masks_warrior = env.action_masks()
    assert not masks_warrior[env._build_road_idx]


def test_build_road_action_calls_headless(env):
    """step(BUILD_ROAD_idx) → invoca env.headless.build_road(save_path, unit.id)."""
    worker = UnitState("Worker", x=1, y=1, movement_points=2.0, id=77)
    state = _mock_state(units=[worker])
    state.tiles_with_road = set()
    env._current_state = state
    env._step_type = "unit"
    env._pending_units = [worker]
    env._unit_rotation_index = 0
    env._buffered_city_action = env._skip_idx

    with patch.object(env.headless, "build_road",
                      return_value={"success": True, "improvement": "Road", "turns": 4}) as mock_br, \
         patch.object(env, "_advance_turn"), \
         patch.object(env, "_advance_tech"), \
         patch.object(env.parser, "parse", return_value=state):
        env.step(env._build_road_idx)

    mock_br.assert_called_once()
    args, _kwargs = mock_br.call_args
    # Argomenti posizionali attesi: (save_path, unit.id).
    assert args[0] == env.save_path
    assert args[1] == worker.id
