import numpy as np
from stable_baselines3.common.callbacks import BaseCallback


class UncivMetricsCallback(BaseCallback):
    """
    Logga metriche custom di Unciv su TensorBoard ad ogni rollout.
    Legge gold, happiness, n_cities, turn, n_techs, population dall'info dict.
    """

    def __init__(self, verbose: int = 0) -> None:
        super().__init__(verbose)
        self._episode_infos: list[dict] = []

    def _on_step(self) -> bool:
        """Raccoglie info da ogni environment step."""
        for info in self.locals.get("infos", []):
            if "episode" in info:
                self._episode_infos.append(info)
        return True

    def _on_rollout_end(self) -> None:
        """Chiamato alla fine di ogni rollout (ogni n_steps * n_envs step)."""
        if not self._episode_infos:
            return

        self.logger.record("unciv/gold_mean",       np.mean([i.get("gold", 0)       for i in self._episode_infos]))
        self.logger.record("unciv/happiness_mean",  np.mean([i.get("happiness", 0)  for i in self._episode_infos]))
        self.logger.record("unciv/cities_mean",     np.mean([i.get("n_cities", 0)   for i in self._episode_infos]))
        self.logger.record("unciv/turns_mean",      np.mean([i.get("turn", 0)       for i in self._episode_infos]))
        self.logger.record("unciv/techs_mean",      np.mean([i.get("n_techs", 0)    for i in self._episode_infos]))
        self.logger.record("unciv/population_mean", np.mean([i.get("population", 0) for i in self._episode_infos]))

        self._episode_infos.clear()


# Fase 2.2c — 19 azioni: 9 edifici + 5 unità + skip + 4 MOVE_*
_ACTION_NAMES = [
    "Barracks", "Colosseum", "Courthouse", "Granary", "Library",
    "Monument", "Stable", "Temple", "Walls",
    "Scout", "Settler", "Spearman", "Warrior", "Worker",
    "Idle",
    "MOVE_NORTH", "MOVE_SOUTH", "MOVE_EAST", "MOVE_WEST",
]


class ActionDistributionCallback(BaseCallback):
    """
    Logga la distribuzione delle azioni per diagnosticare comportamenti degeneri.
    Aggiornato per Fase 2.2c: 19 azioni, include edifici, unità, MOVE_*.
    """

    def __init__(self, log_freq: int = 10_000, verbose: int = 0) -> None:
        super().__init__(verbose)
        self.log_freq = log_freq
        self._action_counts = np.zeros(len(_ACTION_NAMES), dtype=int)

    def _on_step(self) -> bool:
        """Conta azioni eseguite e logga distribuzione ogni log_freq step."""
        actions = self.locals.get("actions", [])
        for a in actions:
            if 0 <= a < len(_ACTION_NAMES):
                self._action_counts[a] += 1

        if self.num_timesteps % self.log_freq == 0 and self._action_counts.sum() > 0:
            total = self._action_counts.sum()
            for i, name in enumerate(_ACTION_NAMES):
                self.logger.record(f"unciv/action_{name}", self._action_counts[i] / total)
            self._action_counts[:] = 0

        return True
