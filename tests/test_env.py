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
    assert env.observation_space.shape == (57,)
    assert env.action_space.n == 19


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
        assert obs.shape == (57,)
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
    assert all(masks[0:7])
    assert not any(masks[7:11])


def test_action_masks_unit_step(env):
    env._step_type = "unit"
    masks = env.action_masks()
    skip = env._skip_idx
    move_s = env._move_start_idx
    assert masks.shape == (len(env.ACTION_MAP),)
    assert not any(masks[:skip])
    assert masks[skip]
    assert all(masks[move_s:move_s + 4])


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


def test_mask_skip_always_true_city_step(env):
    _setup_masking(env, techs_researched=[], built_buildings=["Monument"])
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


def test_unit_step_mask_unchanged(env):
    env._step_type = "unit"
    masks = env.action_masks()
    skip = env._skip_idx
    move_s = env._move_start_idx
    assert masks[skip]
    assert all(masks[move_s:move_s + 4])
    assert not any(masks[:skip])


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

    assert obs.shape == (57,)
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
         patch.object(env.parser, 'parse', return_value=mock_state):
        env._current_state = mock_state
        env._step_type = "unit"
        env._unit_rotation_index = 0
        env._pending_warriors = [warrior]
        env._buffered_city_action = env._skip_idx
        obs, reward, term, trunc, info = env.step(env._skip_idx)

    assert obs.shape == (57,)
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
    """In unit step, obs[53-55] riflettono unità selezionata."""
    warrior = UnitState("Warrior", x=10, y=10, movement_points=2.0)
    mock_state = _mock_state(units=[warrior])
    env._current_state = mock_state
    env._step_type = "unit"
    env._unit_rotation_index = 0
    env._pending_warriors = [warrior]

    obs = env._get_obs()
    assert obs.shape == (57,)
    # x=10/20=0.5, y=10/20=0.5, movement=2/2=1.0
    assert abs(obs[53] - 0.5) < 1e-5
    assert abs(obs[54] - 0.5) < 1e-5
    assert abs(obs[55] - 1.0) < 1e-5
