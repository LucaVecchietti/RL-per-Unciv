import numpy as np
from typing import Optional

from src.parsers.state_parser import GameState
from src.utils.reward import REWARD_WEIGHTS


def compute_reward_verbose(
    prev: Optional[GameState],
    curr: GameState,
    action: int,
    weights: dict = REWARD_WEIGHTS,
) -> tuple[float, dict]:
    """
    Come compute_reward ma restituisce anche il breakdown per componente.
    Utile per diagnosticare comportamenti inattesi durante il training.

    Returns:
        (total_reward, breakdown): float e dizionario componenti.
    """
    if prev is None:
        return 0.0, {}

    breakdown: dict[str, float] = {}
    w = weights

    # --- 1. Crescita popolazione ---
    pop_reward = 0.0
    if prev.cities and curr.cities:
        pop_delta = curr.cities[0].population - prev.cities[0].population
        pop_reward = pop_delta * w["population_growth"]
    breakdown["population_growth"] = pop_reward

    # --- 2. Edifici completati ---
    prev_buildings = set(prev.cities[0].built_buildings) if prev.cities else set()
    curr_buildings = set(curr.cities[0].built_buildings) if curr.cities else set()
    new_buildings = curr_buildings - prev_buildings
    building_reward = len(new_buildings) * w["building_complete"]
    breakdown["building_complete"] = building_reward

    # --- 3. Tecnologie scoperte ---
    new_techs = set(curr.techs_researched) - set(prev.techs_researched)
    tech_reward = len(new_techs) * w["tech_researched"]
    breakdown["tech_researched"] = tech_reward

    # --- 4. Gestione oro ---
    gold_delta = curr.gold - prev.gold
    gold_reward = float(np.clip(gold_delta / 100.0, -w["gold_accumulation"], w["gold_accumulation"]))
    breakdown["gold_accumulation"] = gold_reward

    # --- 5. Penalty happiness negativa ---
    happiness_penalty = 0.0
    if curr.happiness < 0:
        happiness_penalty = curr.happiness * w["happiness_penalty"]
    breakdown["happiness_penalty"] = happiness_penalty

    # --- 6. Penalty azione idle ---
    idle_penalty = -w["idle_penalty"] if action == 6 else 0.0
    breakdown["idle_penalty"] = idle_penalty

    total = float(sum(breakdown.values()))
    return total, breakdown
