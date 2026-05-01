import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from src.envs.unciv_env import UncivEnv


@pytest.fixture
def env(tmp_path):
    # Crea config minimale
    config = {
        "training": {"total_timesteps": 1000},
        "environment": {"max_turns": 50, "map_size": "tiny", "victory_type": "science"},
        "paths": {"save_dir": str(tmp_path / "models"), "log_dir": str(tmp_path / "logs"), "unciv_saves": str(tmp_path / "saves")}
    }
    import yaml
    config_path = tmp_path / "config.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(config, f)
    return UncivEnv(config_path=str(config_path), env_rank=0)


def test_spaces(env):
    assert env.observation_space.shape == (7,)
    assert env.action_space.n == 7


def test_env_rank_uses_separate_save_files(tmp_path):
    """Due env con rank diversi devono usare save file separati."""
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

    env0 = UncivEnv(config_path=str(config_path), env_rank=0)
    env1 = UncivEnv(config_path=str(config_path), env_rank=1)

    assert env0.save_path != env1.save_path
    assert "current_game_0" in str(env0.save_path)
    assert "current_game_1" in str(env1.save_path)


def test_step_output_shape(env):
    with patch.object(env, '_start_new_game'), \
         patch.object(env, '_apply_action'), \
         patch.object(env, '_advance_turn'), \
         patch.object(env.parser, 'parse') as mock_parse:
        from src.parsers.state_parser import GameState, CityState
        mock_state = GameState(10, "India", 200, 5,
            [CityState("Rome", 3, "Monument", [], 200, 0)],
            ["Agriculture"], "Writing", 20, 20)
        mock_parse.return_value = mock_state
        env._current_state = mock_state
        obs, reward, term, trunc, info = env.step(0)
        assert obs.shape == (7,)
        assert isinstance(reward, float)
        assert isinstance(term, bool)
