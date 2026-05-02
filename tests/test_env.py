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


def test_spaces(env):
    assert env.observation_space.shape == (52,)
    assert env.action_space.n == 11


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
        assert obs.shape == (52,)
        assert isinstance(reward, float)
        assert isinstance(term, bool)


def test_action_masks_city_step(env):
    env._step_type = "city"
    masks = env.action_masks()
    assert masks.shape == (11,)
    assert masks.dtype == bool
    assert all(masks[0:7])
    assert not any(masks[7:11])


def test_action_masks_unit_step(env):
    env._step_type = "unit"
    masks = env.action_masks()
    assert masks.shape == (11,)
    assert not any(masks[0:6])
    assert masks[6]
    assert all(masks[7:11])


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

    assert obs.shape == (52,)
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
        env._buffered_city_action = 5
        obs, reward, term, trunc, info = env.step(6)  # skip

    assert obs.shape == (52,)
    assert env._step_type == "city"
    mock_adv.assert_called_once()


def test_obs_contains_selected_unit_coords(env):
    """In unit step, obs[48-50] riflettono unità selezionata."""
    warrior = UnitState("Warrior", x=10, y=10, movement_points=2.0)
    mock_state = _mock_state(units=[warrior])
    env._current_state = mock_state
    env._step_type = "unit"
    env._unit_rotation_index = 0
    env._pending_warriors = [warrior]

    obs = env._get_obs()
    assert obs.shape == (52,)
    # x=10/20=0.5, y=10/20=0.5, movement=2/2=1.0
    assert abs(obs[48] - 0.5) < 1e-5
    assert abs(obs[49] - 0.5) < 1e-5
    assert abs(obs[50] - 1.0) < 1e-5
