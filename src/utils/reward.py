import numpy as np
from typing import Optional

from src.parsers.state_parser import GameState

# Pesi configurabili — non hardcoded nel codice
REWARD_WEIGHTS = {
    "population_growth":  2.0,
    "building_complete":  1.5,
    "tech_researched":    3.0,
    "gold_accumulation":  0.5,
    "happiness_penalty":  0.1,
    "idle_penalty":       0.05,
    "exploration":        0.3,
}


def compute_reward(
    prev: Optional[GameState],
    curr: GameState,
    action: int,
    weights: dict = REWARD_WEIGHTS,
) -> float:
    """
    Calcola la reward per un singolo step.

    Args:
        prev: Stato al turno precedente (None al primo step).
        curr: Stato attuale.
        action: Azione eseguita (0-6).
        weights: Pesi reward — override da config se necessario.

    Returns:
        reward: float, può essere negativa.
    """
    if prev is None:
        return 0.0

    reward = 0.0
    w = weights

    # --- 1. Crescita popolazione ---
    if prev.cities and curr.cities:
        pop_delta = curr.cities[0].population - prev.cities[0].population
        reward += pop_delta * w["population_growth"]

    # --- 2. Edifici completati ---
    prev_buildings = set(prev.cities[0].built_buildings) if prev.cities else set()
    curr_buildings = set(curr.cities[0].built_buildings) if curr.cities else set()
    new_buildings = curr_buildings - prev_buildings
    reward += len(new_buildings) * w["building_complete"]

    # --- 3. Tecnologie scoperte ---
    new_techs = set(curr.techs_researched) - set(prev.techs_researched)
    reward += len(new_techs) * w["tech_researched"]

    # --- 4. Gestione oro ---
    gold_delta = curr.gold - prev.gold
    reward += float(np.clip(gold_delta / 100.0, -w["gold_accumulation"], w["gold_accumulation"]))

    # --- 5. Penalty happiness negativa ---
    if curr.happiness < 0:
        reward += curr.happiness * w["happiness_penalty"]

    # --- 6. Penalty azione idle (fine turno senza fare nulla) ---
    if action == 6:
        reward -= w["idle_penalty"]

    # --- 7. Exploration reward (Fase 2.1) ---
    explored_delta = curr.tiles_explored - prev.tiles_explored
    if explored_delta > 0:
        reward += explored_delta * w["exploration"]

    return float(reward)


def compute_terminal_reward(final_state: GameState, max_turns: int) -> float:
    """
    Reward bonus/malus alla fine dell'episodio.
    Premia la sopravvivenza e la crescita complessiva.

    Chiamare solo su terminated=True, non su truncated=True.
    """
    survival_bonus = 1.0 if final_state.happiness >= 0 else -1.0
    progress_bonus = (
        len(final_state.techs_researched) * 0.1 +
        sum(c.population for c in final_state.cities) * 0.05
    )
    return survival_bonus + progress_bonus
