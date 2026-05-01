import numpy as np
from stable_baselines3.common.callbacks import BaseCallback


class UncivMetricsCallback(BaseCallback):
    """
    Logga metriche custom di Unciv su TensorBoard ad ogni rollout.
    Legge gold, happiness, n_cities, turn dall'info dict di ogni episodio.
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

        gold_values = [i.get("gold", 0) for i in self._episode_infos]
        happiness_values = [i.get("happiness", 0) for i in self._episode_infos]
        cities_values = [i.get("n_cities", 0) for i in self._episode_infos]
        turn_values = [i.get("turn", 0) for i in self._episode_infos]

        self.logger.record("unciv/gold_mean", np.mean(gold_values))
        self.logger.record("unciv/happiness_mean", np.mean(happiness_values))
        self.logger.record("unciv/cities_mean", np.mean(cities_values))
        self.logger.record("unciv/turns_mean", np.mean(turn_values))

        self._episode_infos.clear()


class ActionDistributionCallback(BaseCallback):
    """
    Logga la distribuzione delle azioni per diagnosticare
    comportamenti degeneri (es. agente che sceglie sempre la stessa azione).
    """

    ACTION_NAMES = ["Monument", "Granary", "Library", "Barracks", "Settler", "Warrior", "Idle"]

    def __init__(self, log_freq: int = 10_000, verbose: int = 0) -> None:
        super().__init__(verbose)
        self.log_freq = log_freq
        self._action_counts = np.zeros(7, dtype=int)

    def _on_step(self) -> bool:
        """Conta le azioni eseguite e logga la distribuzione ogni log_freq step."""
        actions = self.locals.get("actions", [])
        for a in actions:
            if 0 <= a < 7:
                self._action_counts[a] += 1

        if self.num_timesteps % self.log_freq == 0 and self._action_counts.sum() > 0:
            total = self._action_counts.sum()
            for i, name in enumerate(self.ACTION_NAMES):
                freq = self._action_counts[i] / total
                self.logger.record(f"unciv/action_{name}", freq)
            self._action_counts[:] = 0

        return True
