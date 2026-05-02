import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from src.utils.callbacks import UncivMetricsCallback, ActionDistributionCallback


def make_callback_ready(cb):
    """Inizializza gli attributi SB3 necessari per i test senza avviare training.

    logger e num_timesteps sono property che delegano a self.model — mock tramite model.
    """
    mock_model = MagicMock()
    mock_model.num_timesteps = 0  # num_timesteps, logger, training_env sono property → delegano a model
    cb.model = mock_model
    cb.locals = {}
    cb.globals = {}
    cb.n_calls = 0
    return cb


def test_unciv_metrics_callback_instantiation():
    cb = UncivMetricsCallback(verbose=0)
    assert cb._episode_infos == []


def test_unciv_metrics_on_step_returns_true():
    cb = make_callback_ready(UncivMetricsCallback())
    cb.locals = {"infos": []}
    result = cb._on_step()
    assert result is True


def test_unciv_metrics_on_rollout_end_empty():
    cb = make_callback_ready(UncivMetricsCallback())
    cb._on_rollout_end()  # non deve lanciare eccezioni con lista vuota


def test_unciv_metrics_on_rollout_end_logs():
    cb = make_callback_ready(UncivMetricsCallback())
    cb._episode_infos = [
        {"gold": 200, "happiness": 5, "n_cities": 1, "turn": 50},
        {"gold": 300, "happiness": 3, "n_cities": 1, "turn": 80},
    ]
    cb._on_rollout_end()
    cb.logger.record.assert_called()
    assert cb._episode_infos == []  # resettata dopo log


def test_unciv_metrics_collects_episode_info():
    cb = make_callback_ready(UncivMetricsCallback())
    cb.locals = {"infos": [{"episode": {"r": 10}, "gold": 100, "happiness": 5, "n_cities": 1, "turn": 20}]}
    cb._on_step()
    assert len(cb._episode_infos) == 1


def test_action_distribution_callback_instantiation():
    cb = ActionDistributionCallback(log_freq=5000)
    assert cb.log_freq == 5000
    assert cb._action_counts.shape == (11,)


def test_action_distribution_on_step_returns_true():
    cb = make_callback_ready(ActionDistributionCallback())
    cb.locals = {"actions": [0, 1, 2]}
    result = cb._on_step()
    assert result is True


def test_action_distribution_counts_actions():
    cb = make_callback_ready(ActionDistributionCallback(log_freq=100_000))
    cb.num_timesteps = 1  # plain attr — 1 % 100_000 != 0 → no log+reset
    cb.locals = {"actions": [0, 0, 6]}
    cb._on_step()
    assert cb._action_counts[0] == 2
    assert cb._action_counts[6] == 1


def test_analyze_run_missing_file(tmp_path, capsys):
    from src.utils.analyze_run import analyze_evaluations
    analyze_evaluations(str(tmp_path))
    captured = capsys.readouterr()
    assert "evaluations.npz" in captured.out


def test_analyze_run_with_data(tmp_path, capsys):
    from src.utils.analyze_run import analyze_evaluations
    timesteps = np.array([10_000, 50_000])
    results = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    np.savez(tmp_path / "evaluations.npz", timesteps=timesteps, results=results)
    analyze_evaluations(str(tmp_path))
    captured = capsys.readouterr()
    assert "10,000" in captured.out or "10000" in captured.out
