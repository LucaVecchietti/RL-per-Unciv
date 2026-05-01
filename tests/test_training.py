import pytest
import yaml
from pathlib import Path


def test_load_config(tmp_path):
    from train import load_config
    cfg = {
        "training": {"total_timesteps": 1000, "n_envs": 1, "learning_rate": 3e-4,
                     "n_steps": 64, "batch_size": 64, "n_epochs": 2, "gamma": 0.99, "clip_range": 0.2},
        "environment": {"max_turns": 10, "map_size": "tiny", "victory_type": "science"},
        "paths": {"save_dir": str(tmp_path / "models"), "log_dir": str(tmp_path / "logs"),
                  "unciv_saves": str(tmp_path / "saves")},
    }
    config_path = tmp_path / "config.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(cfg, f)

    loaded = load_config(str(config_path))
    assert loaded["training"]["n_envs"] == 1
    assert loaded["paths"]["log_dir"] == str(tmp_path / "logs")


def test_make_env_returns_callable(tmp_path):
    from train import make_env
    cfg = {
        "training": {"total_timesteps": 100, "n_envs": 1, "learning_rate": 3e-4,
                     "n_steps": 64, "batch_size": 64, "n_epochs": 2, "gamma": 0.99, "clip_range": 0.2},
        "environment": {"max_turns": 10, "map_size": "tiny", "victory_type": "science"},
        "paths": {"save_dir": str(tmp_path / "models"), "log_dir": str(tmp_path / "logs"),
                  "unciv_saves": str(tmp_path / "saves")},
    }
    config_path = tmp_path / "config.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(cfg, f)

    factory = make_env(str(config_path))
    assert callable(factory)


def test_train_module_imports():
    import train
    assert hasattr(train, "train")
    assert hasattr(train, "load_config")
    assert hasattr(train, "make_env")


def test_evaluate_module_imports():
    import evaluate
    assert hasattr(evaluate, "evaluate")
