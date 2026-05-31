import numpy as np
from typing import Optional

from src.parsers.state_parser import GameState

# Pesi configurabili — non hardcoded nel codice.
# File 23.1: rework shaping reward (stats accumulate, risorse tipizzate,
# cities_alive_bonus, tech_progress, units_stuck_penalty, happiness_bonus,
# building_diversity). Mirror 1:1 in `config/default_config.yaml` → `reward:`.
REWARD_WEIGHTS = {
    # --- Legacy (invariati) ---
    "population_growth":  2.0,
    "building_complete":  1.5,
    "tech_researched":    3.0,
    "gold_accumulation":  0.5,
    "happiness_penalty":  0.1,
    "idle_penalty":       0.05,
    "exploration":        0.3,
    "resource_placement": 2.0,

    # --- Modificati in File 23.1 / Sessione 45.1 ---
    "found_city": 6.0,  # 23.1 lo aveva ridotto a 3.0; 45.1 lo riporta a 6.0 per rompere lo stallo cities_founded (diagnosi rl-trainer Run #23)

    # --- Nuovi in File 23.1: risorse connesse tipizzate (ex resource_connected) ---
    "resource_connected_bonus":     3.0,
    "resource_connected_strategic": 4.0,
    "resource_connected_luxury":    5.0,

    # --- Nuovi in File 23.1: espansione continua ---
    "cities_alive_bonus": 0.15,  # per ogni città oltre la prima, per turno (45.1: 0.05→0.15 per pareggiare farming mono-città)

    # --- Nuovi in File 23.1: stats accumulate (delta clip ≥ 0) ---
    "science_accumulated":   0.25,
    "gold_accumulated":      0.25,
    "culture_accumulated":   0.25,
    "happiness_accumulated": 0.25,
    "faith_accumulated":     0.25,  # inerte finché faith_per_turn=0 nel parser

    # --- Nuovi in File 23.1: shaping aggiuntivi ---
    "tech_progress":        0.5,   # delta normalizzato (progress/cost), clip [0,1]
    "units_stuck_penalty":  0.02,  # per unità stuck nel turno
    "happiness_bonus":      0.05,  # cap implicito = peso (one-shot per turno)
    "building_diversity":   0.2,   # una tantum per ogni building nuovo nel set civ (45.1: 0.5→0.2 per ridurre farming bias mono-città)
}


def compute_reward(
    prev: Optional[GameState],
    curr: GameState,
    action: int,
    weights: dict = REWARD_WEIGHTS,
    skip_action_idx: int = 6,
) -> float:
    """
    Calcola la reward per un singolo step.

    Args:
        prev: Stato al turno precedente (None al primo step).
        curr: Stato attuale.
        action: Azione eseguita.
        weights: Pesi reward — override da config se necessario.
        skip_action_idx: Indice dell'azione skip/idle nell'ACTION_MAP corrente.

    Returns:
        reward: float, può essere negativa.
    """
    if prev is None:
        return 0.0

    reward = 0.0
    w = weights

    # --- 1. Crescita popolazione (somma su tutte le città) ---
    pop_delta = sum(c.population for c in curr.cities) - sum(c.population for c in prev.cities)
    reward += pop_delta * w["population_growth"]

    # --- 2. Edifici completati (somma su tutte le città) ---
    prev_buildings_count = sum(len(c.built_buildings) for c in prev.cities)
    curr_buildings_count = sum(len(c.built_buildings) for c in curr.cities)
    reward += max(0, curr_buildings_count - prev_buildings_count) * w["building_complete"]

    # --- 2b. Fondazione di una nuova città (peso ridotto in File 23.1: 3.0) ---
    new_cities = len(curr.cities) - len(prev.cities)
    if new_cities > 0:
        reward += new_cities * w["found_city"]

    # --- 2c. Risorse Strategic/Luxury catturate nel territorio (Fase C2) ---
    prev_res = sum(c.territory_strategic + c.territory_luxury for c in prev.cities)
    curr_res = sum(c.territory_strategic + c.territory_luxury for c in curr.cities)
    if curr_res > prev_res:
        reward += (curr_res - prev_res) * w["resource_placement"]

    # --- 2d. Risorse connesse tipizzate (File 23.1: split Bonus / Strategic / Luxury) ---
    # NB: connected_bonus può non esistere ancora finché unciv-engine non lo popola.
    # Usiamo getattr per robustezza, anche se il dataclass default a 0 dovrebbe coprire.
    prev_conn_bonus = getattr(prev, "connected_bonus", 0)
    curr_conn_bonus = getattr(curr, "connected_bonus", 0)
    delta_conn_bonus = max(0, curr_conn_bonus - prev_conn_bonus)
    if delta_conn_bonus > 0:
        reward += delta_conn_bonus * w["resource_connected_bonus"]

    delta_conn_strat = max(0, curr.connected_strategic - prev.connected_strategic)
    if delta_conn_strat > 0:
        reward += delta_conn_strat * w["resource_connected_strategic"]

    delta_conn_lux = max(0, curr.connected_luxury - prev.connected_luxury)
    if delta_conn_lux > 0:
        reward += delta_conn_lux * w["resource_connected_luxury"]

    # --- 3. Tecnologie scoperte ---
    new_techs = set(curr.techs_researched) - set(prev.techs_researched)
    reward += len(new_techs) * w["tech_researched"]

    # --- 3b. Tech progress (File 23.1): delta normalizzato (progress/cost) clip [0,1] ---
    if "tech_progress" in w:
        prev_cost = max(getattr(prev, "current_tech_cost", 1.0), 1.0)
        curr_cost = max(getattr(curr, "current_tech_cost", 1.0), 1.0)
        prev_ratio = float(np.clip(getattr(prev, "current_tech_progress", 0.0) / prev_cost, 0.0, 1.0))
        curr_ratio = float(np.clip(getattr(curr, "current_tech_progress", 0.0) / curr_cost, 0.0, 1.0))
        # Su cambio tech, curr_ratio può azzerarsi: clippiamo a 0 il delta negativo.
        delta_ratio = max(0.0, curr_ratio - prev_ratio)
        reward += delta_ratio * w["tech_progress"]

    # --- 4. Gestione oro (clip ±gold_accumulation) ---
    gold_delta = curr.gold - prev.gold
    reward += float(np.clip(gold_delta / 100.0, -w["gold_accumulation"], w["gold_accumulation"]))

    # --- 5. Penalty happiness negativa ---
    if curr.happiness < 0:
        reward += curr.happiness * w["happiness_penalty"]

    # --- 5b. Happiness bonus (File 23.1): cap = peso, se happiness > 5 ---
    if "happiness_bonus" in w and curr.happiness > 5:
        reward += min(w["happiness_bonus"], w["happiness_bonus"])  # cap implicito

    # --- 6. Penalty azione idle (fine turno senza fare nulla) ---
    if action == skip_action_idx:
        reward -= w["idle_penalty"]

    # --- 7. Exploration reward (Fase 2.1) ---
    explored_delta = curr.tiles_explored - prev.tiles_explored
    if explored_delta > 0:
        reward += explored_delta * w["exploration"]

    # --- 8. Cities alive bonus (File 23.1): continuo per turno, città oltre la prima ---
    if "cities_alive_bonus" in w:
        extra_cities = max(0, len(curr.cities) - 1)
        reward += extra_cities * w["cities_alive_bonus"]

    # --- 9. Stats accumulate (File 23.1): delta clip ≥ 0 per 5 statistiche ---
    # Sorgenti per-turn: science/gold/culture dal parser; happiness sul livello accumulato;
    # faith dal nuovo campo faith_per_turn (oggi 0 → blocco inerte).
    if "science_accumulated" in w:
        delta_sci = max(0.0, curr.science_per_turn - prev.science_per_turn)
        reward += w["science_accumulated"] * delta_sci

    if "gold_accumulated" in w:
        # Su delta del gold_per_turn (non del cumulato — quello è già in gold_accumulation).
        delta_gpt = max(0.0, curr.gold_per_turn - prev.gold_per_turn)
        reward += w["gold_accumulated"] * delta_gpt

    if "culture_accumulated" in w:
        delta_cul = max(0.0, curr.culture_per_turn - prev.culture_per_turn)
        reward += w["culture_accumulated"] * delta_cul

    if "happiness_accumulated" in w:
        # Per happiness: livello accumulato, non per-turn.
        delta_hap = max(0.0, curr.happiness - prev.happiness)
        reward += w["happiness_accumulated"] * delta_hap

    if "faith_accumulated" in w:
        prev_faith = getattr(prev, "faith_per_turn", 0.0)
        curr_faith = getattr(curr, "faith_per_turn", 0.0)
        delta_faith = max(0.0, curr_faith - prev_faith)
        reward += w["faith_accumulated"] * delta_faith

    # --- 10. Units stuck penalty (File 23.1) ---
    # `curr.units_stuck` è settato dall'env DOPO il parsing (cfr. _advance_game_turn).
    # Conta le unità con movement_points>0 senza mosse legali nel turno corrente.
    if "units_stuck_penalty" in w:
        n_stuck = getattr(curr, "units_stuck", 0)
        if n_stuck > 0:
            reward -= w["units_stuck_penalty"] * n_stuck

    # --- 11. Building diversity (File 23.1): una tantum per building nuovo ---
    # Set cumulato dei building visti a livello civ: confrontiamo l'unione dei built_buildings
    # tra prev e curr. Ogni building presente in curr ma non in prev = +peso (una tantum
    # nel turno; il fatto che il building resti nel set per i turni successivi lo rende
    # impatto-cap naturale).
    if "building_diversity" in w:
        prev_buildings_set: set[str] = {b for c in prev.cities for b in c.built_buildings}
        curr_buildings_set: set[str] = {b for c in curr.cities for b in c.built_buildings}
        new_distinct = curr_buildings_set - prev_buildings_set
        if new_distinct:
            reward += w["building_diversity"] * len(new_distinct)

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
