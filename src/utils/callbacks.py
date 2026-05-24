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

        infos = self._episode_infos

        self.logger.record("unciv/gold_mean",       np.mean([i.get("gold", 0)       for i in infos]))
        self.logger.record("unciv/happiness_mean",  np.mean([i.get("happiness", 0)  for i in infos]))
        self.logger.record("unciv/cities_mean",     np.mean([i.get("n_cities", 0)   for i in infos]))
        self.logger.record("unciv/turns_mean",      np.mean([i.get("turn", 0)       for i in infos]))
        self.logger.record("unciv/techs_mean",      np.mean([i.get("n_techs", 0)    for i in infos]))
        self.logger.record("unciv/population_mean", np.mean([i.get("population", 0) for i in infos]))

        # File 19 — metriche per turno (media episodi)
        self.logger.record("unciv/tiles_explored_mean",   np.mean([i.get("tiles_explored", 0)      for i in infos]))
        self.logger.record("unciv/city_territory_mean",   np.mean([i.get("city_territory_tiles", 0) for i in infos]))
        self.logger.record("unciv/science_per_turn_mean", np.mean([i.get("science_per_turn", 0)    for i in infos]))
        self.logger.record("unciv/culture_per_turn_mean", np.mean([i.get("culture_per_turn", 0)    for i in infos]))

        # File 19 — totali episodio
        self.logger.record("unciv/ep_total_gold_mean",    np.mean([i.get("ep_total_gold", 0)    for i in infos]))
        self.logger.record("unciv/ep_total_science_mean", np.mean([i.get("ep_total_science", 0) for i in infos]))
        self.logger.record("unciv/ep_total_culture_mean", np.mean([i.get("ep_total_culture", 0) for i in infos]))

        # File 19 — costruzioni completate per tipo
        for b in ["Monument", "Granary", "Library", "Barracks", "Temple", "Colosseum", "Walls", "Stable", "Courthouse"]:
            self.logger.record(
                f"unciv/built_{b.lower()}_mean",
                np.mean([i.get("ep_buildings_built", {}).get(b, 0) for i in infos]),
            )

        # File 19 — unità create per tipo
        for u in ["Warrior", "Scout", "Settler", "Worker", "Spearman"]:
            self.logger.record(
                f"unciv/trained_{u.lower()}_mean",
                np.mean([i.get("ep_units_built", {}).get(u, 0) for i in infos]),
            )

        # File 19 — risorse (totale strategiche e luxury, media episodi)
        self.logger.record(
            "unciv/strategic_res_count_mean",
            np.mean([sum(i.get("strategic_resources", {}).values()) for i in infos]),
        )
        self.logger.record(
            "unciv/luxury_res_count_mean",
            np.mean([sum(i.get("luxury_resources", {}).values()) for i in infos]),
        )

        # File 21 — metriche movimento
        self.logger.record("unciv/moves_attempted_mean",      np.mean([i.get("moves_attempted", 0)      for i in infos]))
        self.logger.record("unciv/moves_succeeded_mean",      np.mean([i.get("moves_succeeded", 0)      for i in infos]))
        self.logger.record("unciv/moves_illegal_mean",        np.mean([i.get("moves_illegal", 0)        for i in infos]))
        self.logger.record("unciv/move_cost_mean",            np.mean([i.get("move_cost_mean", 0)       for i in infos]))
        self.logger.record("unciv/units_stuck_mean",          np.mean([i.get("units_stuck", 0)          for i in infos]))
        self.logger.record("unciv/legal_moves_available_mean", np.mean([i.get("legal_moves_available", 0) for i in infos]))
        self.logger.record("unciv/new_tiles_per_move_mean",   np.mean([i.get("new_tiles_per_move", 0)   for i in infos]))
        for u in ["Warrior", "Scout", "Settler", "Worker", "Spearman"]:
            self.logger.record(
                f"unciv/moved_{u.lower()}_mean",
                np.mean([i.get("moved_by_type", {}).get(u, 0) for i in infos]),
            )

        self._episode_infos.clear()


# Fase 2.B — 21 azioni: 9 edifici + 5 unità + skip + 6 direzioni hex (clock)
_ACTION_NAMES = [
    "Barracks", "Colosseum", "Courthouse", "Granary", "Library",
    "Monument", "Stable", "Temple", "Walls",
    "Scout", "Settler", "Spearman", "Warrior", "Worker",
    "Idle",
    "MOVE_2", "MOVE_4", "MOVE_6", "MOVE_8", "MOVE_10", "MOVE_12",
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
