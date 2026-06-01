import pytest
from src.parsers.state_parser import GameState, CityState
from src.utils.reward import compute_reward, compute_terminal_reward, REWARD_WEIGHTS


def make_state(
    turn: int = 10,
    gold: float = 200.0,
    happiness: float = 5.0,
    population: int = 3,
    buildings: list[str] = None,
    techs: list[str] = None,
) -> GameState:
    return GameState(
        turn=turn,
        current_player="India",
        gold=gold,
        happiness=happiness,
        cities=[CityState("Rome", population, "Monument", buildings or [], 200, 0)],
        techs_researched=techs or ["Agriculture"],
        current_tech="Writing",
        map_width=20,
        map_height=20,
    )


def test_prev_none_returns_zero():
    curr = make_state()
    assert compute_reward(None, curr, action=0) == 0.0


def test_population_growth_positive():
    prev = make_state(population=3)
    curr = make_state(population=4)
    reward = compute_reward(prev, curr, action=0)
    assert reward > 0.0


def test_new_building_positive():
    prev = make_state(buildings=[])
    curr = make_state(buildings=["Granary"])
    reward = compute_reward(prev, curr, action=1)
    assert reward > 0.0


def test_new_tech_positive():
    prev = make_state(techs=["Agriculture"])
    curr = make_state(techs=["Agriculture", "Mining"])
    reward = compute_reward(prev, curr, action=0)
    assert reward > 0.0


def test_found_city_bonus():
    """Fondare una nuova città dà almeno il bonus found_city."""
    prev = make_state()  # 1 città
    curr = GameState(
        turn=11, current_player="India", gold=200, happiness=5,
        cities=[
            CityState("Rome", 3, "Monument", [], 200, 0),
            CityState("Delhi", 1, "", [], 200, 0),
        ],
        techs_researched=["Agriculture"], current_tech="Writing",
        map_width=20, map_height=20,
    )
    reward = compute_reward(prev, curr, action=0)
    assert reward >= REWARD_WEIGHTS["found_city"]


def test_resource_placement_bonus():
    """Catturare tile-risorsa nel territorio dà il bonus resource_placement."""
    prev = make_state()  # territory_strategic/luxury = 0
    curr_city = CityState("Rome", 3, "Monument", [], 200, 0)
    curr_city.territory_strategic = 2
    curr = GameState(
        turn=11, current_player="India", gold=200, happiness=5,
        cities=[curr_city], techs_researched=["Agriculture"], current_tech="Writing",
        map_width=20, map_height=20,
    )
    reward = compute_reward(prev, curr, action=0)
    assert reward >= 2 * REWARD_WEIGHTS["resource_placement"]


def test_resource_connected_bonus():
    """Connettere risorse strategiche → bonus tipizzato (File 23.1).

    Il vecchio peso `resource_connected` è stato sostituito da 3 pesi tipizzati:
    `resource_connected_{bonus,strategic,luxury}`. Qui verifichiamo il caso strategico.
    """
    prev = make_state()  # connected_strategic/luxury = 0
    curr = GameState(
        turn=11, current_player="India", gold=200, happiness=5,
        cities=[CityState("Rome", 3, "Monument", [], 200, 0)],
        techs_researched=["Agriculture"], current_tech="Writing",
        map_width=20, map_height=20, connected_strategic=2,
    )
    reward = compute_reward(prev, curr, action=0)
    assert reward >= 2 * REWARD_WEIGHTS["resource_connected_strategic"]


def test_gold_increase_positive():
    prev = make_state(gold=100.0)
    curr = make_state(gold=200.0)
    reward = compute_reward(prev, curr, action=0)
    assert reward > 0.0


def test_negative_happiness_penalty():
    prev = make_state(happiness=-5.0)
    curr = make_state(happiness=-5.0)
    reward = compute_reward(prev, curr, action=0)
    assert reward < 0.0


def test_idle_action_penalty():
    prev = make_state()
    curr = make_state()
    reward_idle = compute_reward(prev, curr, action=6)
    reward_build = compute_reward(prev, curr, action=0)
    assert reward_idle < reward_build


def test_terminal_reward_positive_happiness():
    state = make_state(happiness=5.0, techs=["Agriculture", "Mining"], population=3)
    r = compute_terminal_reward(state, max_turns=200)
    assert r > 0.0


def test_terminal_reward_negative_happiness():
    state = make_state(happiness=-5.0)
    r = compute_terminal_reward(state, max_turns=200)
    assert r < 0.0


def test_exploration_reward():
    from src.parsers.state_parser import GameState, CityState
    prev = GameState(10, "India", 200, 5,
        [CityState("Rome", 3, "Monument", [], 200, 0)],
        ["Agriculture"], "Writing", 20, 20, tiles_explored=10, total_tiles=100)
    curr = GameState(11, "India", 200, 5,
        [CityState("Rome", 3, "Monument", [], 200, 0)],
        ["Agriculture"], "Writing", 20, 20, tiles_explored=15, total_tiles=100)
    reward = compute_reward(prev, curr, action=0)
    assert reward > 0.0  # 5 nuove tile * 0.3 = +1.5


def test_return_type_float():
    prev = make_state()
    curr = make_state()
    reward = compute_reward(prev, curr, action=0)
    assert isinstance(reward, float)


# ---------------------------------------------------------------------------
# File 23.1 — Reward rework: risorse tipizzate, stats accumulate, cities_alive
# ---------------------------------------------------------------------------
#
# I test che seguono assumono i nuovi pesi in REWARD_WEIGHTS:
#   resource_connected_bonus=3.0, resource_connected_strategic=4.0,
#   resource_connected_luxury=5.0, science_accumulated=0.25,
#   gold_accumulated=0.25, culture_accumulated=0.25,
#   happiness_accumulated=0.25, faith_accumulated=0.25,
#   cities_alive_bonus=0.15 (Sessione 45.1: 0.05→0.15), found_city=6.0
#   (Sessione 45.1: 3.0→6.0 per rompere stallo cities_founded),
#   tech_progress=0.5, units_stuck_penalty=0.02, happiness_bonus=0.05,
#   building_diversity=0.2 (Sessione 45.1: 0.5→0.2).
#
# E i nuovi campi su GameState/CityState:
#   GameState.connected_bonus, GameState.faith_per_turn, GameState.units_stuck,
#   CityState.territory_bonus.


def _gs(
    turn: int = 10,
    gold: float = 200.0,
    happiness: float = 5.0,
    cities: list[CityState] | None = None,
    techs: list[str] | None = None,
    current_tech: str | None = "Writing",
    current_tech_progress: float = 0.0,
    current_tech_cost: float = 60.0,
    science_per_turn: float = 0.0,
    gold_per_turn: float = 0.0,
    culture_per_turn: float = 0.0,
    faith_per_turn: float = 0.0,
    connected_bonus: int = 0,
    connected_strategic: int = 0,
    connected_luxury: int = 0,
    units_stuck: int = 0,
) -> GameState:
    """Helper per costruire GameState con i nuovi campi opzionali di File 23.1.

    Backward compatible: setta i nuovi campi solo se presenti su GameState (i test
    falliranno con AttributeError se la dataclass non li espone — comportamento voluto).
    """
    state = GameState(
        turn=turn,
        current_player="India",
        gold=gold,
        happiness=happiness,
        cities=cities if cities is not None else [CityState("Rome", 3, "Monument", [], 200, 0)],
        techs_researched=techs or ["Agriculture"],
        current_tech=current_tech,
        map_width=20,
        map_height=20,
        science_per_turn=science_per_turn,
        culture_per_turn=culture_per_turn,
        current_tech_progress=current_tech_progress,
        current_tech_cost=current_tech_cost,
        gold_per_turn=gold_per_turn,
        connected_strategic=connected_strategic,
        connected_luxury=connected_luxury,
    )
    # Nuovi campi File 23.1 (settati post-construct per non assumere ordine kwargs)
    state.connected_bonus = connected_bonus
    state.faith_per_turn = faith_per_turn
    state.units_stuck = units_stuck
    return state


# --- Risorse tipizzate ---------------------------------------------------------

def test_resource_connected_bonus_3() -> None:
    """Incremento di connected_bonus → reward include +3.0."""
    prev = _gs(connected_bonus=0)
    curr = _gs(connected_bonus=1)
    reward = compute_reward(prev, curr, action=0)
    assert reward >= REWARD_WEIGHTS["resource_connected_bonus"]
    # contributo esatto di questa componente
    assert reward == pytest.approx(REWARD_WEIGHTS["resource_connected_bonus"], abs=1e-6)


def test_resource_connected_strategic_4() -> None:
    """Incremento di connected_strategic → reward include +4.0."""
    prev = _gs(connected_strategic=0)
    curr = _gs(connected_strategic=1)
    reward = compute_reward(prev, curr, action=0)
    assert reward >= REWARD_WEIGHTS["resource_connected_strategic"]
    assert reward == pytest.approx(REWARD_WEIGHTS["resource_connected_strategic"], abs=1e-6)


def test_resource_connected_luxury_5() -> None:
    """Incremento di connected_luxury → reward include +5.0."""
    prev = _gs(connected_luxury=0)
    curr = _gs(connected_luxury=1)
    reward = compute_reward(prev, curr, action=0)
    assert reward >= REWARD_WEIGHTS["resource_connected_luxury"]
    assert reward == pytest.approx(REWARD_WEIGHTS["resource_connected_luxury"], abs=1e-6)


def test_resource_connected_no_change_zero() -> None:
    """Risorse connesse invariate → contributo 0 dai 3 blocchi tipizzati."""
    prev = _gs(connected_bonus=2, connected_strategic=1, connected_luxury=1)
    curr = _gs(connected_bonus=2, connected_strategic=1, connected_luxury=1)
    reward = compute_reward(prev, curr, action=0)
    # nessun delta su nulla → reward esattamente 0
    assert reward == pytest.approx(0.0, abs=1e-6)


# --- Stats accumulate (peso 0.25, clip ≥0) ------------------------------------

def test_stats_accumulated_positive_delta_science() -> None:
    """Delta positivo science_per_turn → +0.25 * delta."""
    prev = _gs(science_per_turn=10.0)
    curr = _gs(science_per_turn=15.0)
    reward = compute_reward(prev, curr, action=0)
    assert reward == pytest.approx(0.25 * 5.0, abs=1e-6)


def test_stats_accumulated_positive_delta_gold() -> None:
    """Delta positivo gold_per_turn → +0.25 * delta."""
    prev = _gs(gold_per_turn=4.0)
    curr = _gs(gold_per_turn=10.0)
    reward = compute_reward(prev, curr, action=0)
    assert reward == pytest.approx(0.25 * 6.0, abs=1e-6)


def test_stats_accumulated_positive_delta_culture() -> None:
    """Delta positivo culture_per_turn → +0.25 * delta."""
    prev = _gs(culture_per_turn=2.0)
    curr = _gs(culture_per_turn=5.0)
    reward = compute_reward(prev, curr, action=0)
    assert reward == pytest.approx(0.25 * 3.0, abs=1e-6)


def test_stats_accumulated_positive_delta_happiness() -> None:
    """Delta positivo happiness → +0.25 * delta (clip ≥ 0)."""
    prev = _gs(happiness=5.0)
    curr = _gs(happiness=9.0)
    reward = compute_reward(prev, curr, action=0)
    # Il contributo della componente happiness_accumulated è almeno 0.25 * 4 = 1.0;
    # se l'implementazione include anche happiness_bonus (cap 0.05) il totale è 1.05.
    expected_min = 0.25 * 4.0
    assert reward >= expected_min - 1e-6
    assert reward <= expected_min + REWARD_WEIGHTS["happiness_bonus"] + 1e-6


def test_stats_accumulated_positive_delta_faith() -> None:
    """Delta positivo faith_per_turn → +0.25 * delta."""
    prev = _gs(faith_per_turn=1.0)
    curr = _gs(faith_per_turn=4.0)
    reward = compute_reward(prev, curr, action=0)
    assert reward == pytest.approx(0.25 * 3.0, abs=1e-6)


def test_stats_accumulated_zero_delta() -> None:
    """Stats uguali → contributo 0."""
    prev = _gs(
        science_per_turn=10.0, gold_per_turn=5.0, culture_per_turn=3.0,
        happiness=5.0, faith_per_turn=2.0,
    )
    curr = _gs(
        science_per_turn=10.0, gold_per_turn=5.0, culture_per_turn=3.0,
        happiness=5.0, faith_per_turn=2.0,
    )
    reward = compute_reward(prev, curr, action=0)
    assert reward == pytest.approx(0.0, abs=1e-6)


def test_stats_accumulated_negative_clipped_zero() -> None:
    """Delta negativo su tutte le stats → 0 (no penalty).

    Usiamo happiness=5.0 (≤ soglia) per non attivare happiness_bonus, isolando
    la verifica sul clip ≥0 dei delta negativi delle 5 stats accumulate.
    """
    prev = _gs(
        science_per_turn=20.0, gold_per_turn=10.0, culture_per_turn=8.0,
        happiness=5.0, faith_per_turn=5.0,
    )
    curr = _gs(
        science_per_turn=5.0, gold_per_turn=2.0, culture_per_turn=1.0,
        happiness=5.0, faith_per_turn=0.0,
    )
    reward = compute_reward(prev, curr, action=0)
    assert reward == pytest.approx(0.0, abs=1e-6)


# --- Cities alive bonus -------------------------------------------------------

def test_cities_alive_bonus_one_city() -> None:
    """Una sola città → contributo 0 (bonus per città oltre la prima)."""
    prev = _gs(cities=[CityState("Rome", 3, "Monument", [], 200, 0)])
    curr = _gs(cities=[CityState("Rome", 3, "Monument", [], 200, 0)])
    reward = compute_reward(prev, curr, action=0)
    assert reward == pytest.approx(0.0, abs=1e-6)


def test_cities_alive_bonus_three_cities() -> None:
    """Tre città stabili (no fondazione) → bonus 0.05 * 2 = 0.10."""
    cities = [
        CityState("Rome", 3, "Monument", [], 200, 0),
        CityState("Delhi", 3, "Monument", [], 200, 0),
        CityState("Mumbai", 3, "Monument", [], 200, 0),
    ]
    prev = _gs(cities=[CityState(c.name, c.population, c.current_construction,
                                  list(c.built_buildings), c.health, c.tiles_count) for c in cities])
    curr = _gs(cities=[CityState(c.name, c.population, c.current_construction,
                                  list(c.built_buildings), c.health, c.tiles_count) for c in cities])
    reward = compute_reward(prev, curr, action=0)
    expected = 2 * REWARD_WEIGHTS["cities_alive_bonus"]
    assert reward == pytest.approx(expected, abs=1e-6)


# --- Found city ridotto -------------------------------------------------------

def test_found_city_reduced_to_3() -> None:
    """Fondazione nuova città → REWARD_WEIGHTS["found_city"] + cities_alive_bonus.

    Sessione 45.1: il peso è tornato a 6.0 (era 3.0 in File 23.1, era 5.0 prima).
    Il test resta valido perché compara il delta col valore corrente del peso —
    il nome legacy `_reduced_to_3` non riflette più il valore ma il test isola
    correttamente found_city + cities_alive_bonus (1 città oltre la prima) dal
    population_growth (popolazione totale invariata).
    """
    prev = _gs(cities=[CityState("Rome", 3, "Monument", [], 200, 0)])
    curr = _gs(cities=[
        CityState("Rome", 2, "Monument", [], 200, 0),
        CityState("Delhi", 1, "", [], 200, 0),
    ])
    reward = compute_reward(prev, curr, action=0)
    # contributo found_city + cities_alive_bonus(1 città oltre la prima)
    expected = REWARD_WEIGHTS["found_city"] + REWARD_WEIGHTS["cities_alive_bonus"]
    assert reward == pytest.approx(expected, abs=1e-6)


# --- Tech progress ------------------------------------------------------------

def test_tech_progress_delta_positive() -> None:
    """Incremento di progress/cost → reward proporzionale al delta normalizzato."""
    prev = _gs(current_tech="Writing", current_tech_progress=10.0, current_tech_cost=50.0)
    curr = _gs(current_tech="Writing", current_tech_progress=20.0, current_tech_cost=50.0)
    reward = compute_reward(prev, curr, action=0)
    # Δ(progress/cost) = (20/50 - 10/50) = 0.2 → 0.2 * 0.5 = 0.1
    expected = 0.2 * REWARD_WEIGHTS["tech_progress"]
    assert reward == pytest.approx(expected, abs=1e-6)


def test_tech_progress_no_increment() -> None:
    """Stesso progress → 0."""
    prev = _gs(current_tech="Writing", current_tech_progress=10.0, current_tech_cost=50.0)
    curr = _gs(current_tech="Writing", current_tech_progress=10.0, current_tech_cost=50.0)
    reward = compute_reward(prev, curr, action=0)
    assert reward == pytest.approx(0.0, abs=1e-6)


def test_tech_progress_clip_when_tech_completed() -> None:
    """Tech completata (progress resettato) → nessuna penalty negativa da delta.

    Caso reale: prev ha Writing in progresso a 50/55, curr ha Writing completata e
    nuova tech a 0. Il delta normalizzato grezzo sarebbe negativo, ma deve essere
    clippato a 0 (il completamento è già premiato da tech_researched).
    """
    prev = _gs(
        techs=["Agriculture"],
        current_tech="Writing",
        current_tech_progress=50.0,
        current_tech_cost=55.0,
    )
    curr = _gs(
        techs=["Agriculture", "Writing"],
        current_tech="Mining",
        current_tech_progress=0.0,
        current_tech_cost=35.0,
    )
    reward = compute_reward(prev, curr, action=0)
    # tech_researched (+3.0) deve esserci; tech_progress NON deve sottrarre
    assert reward >= REWARD_WEIGHTS["tech_researched"] - 1e-6


# --- Units stuck penalty ------------------------------------------------------

def test_units_stuck_penalty_proportional() -> None:
    """5 unità stuck → -0.02 * 5 = -0.10."""
    prev = _gs(units_stuck=0)
    curr = _gs(units_stuck=5)
    reward = compute_reward(prev, curr, action=0)
    expected = -5 * REWARD_WEIGHTS["units_stuck_penalty"]
    assert reward == pytest.approx(expected, abs=1e-6)


def test_units_stuck_zero_no_penalty() -> None:
    """Nessuna unità stuck → contributo 0."""
    prev = _gs(units_stuck=0)
    curr = _gs(units_stuck=0)
    reward = compute_reward(prev, curr, action=0)
    assert reward == pytest.approx(0.0, abs=1e-6)


# --- Happiness bonus (cap) ----------------------------------------------------

def test_happiness_bonus_above_threshold() -> None:
    """happiness=10 (>5) → reward include +0.05 (cap)."""
    prev = _gs(happiness=10.0)
    curr = _gs(happiness=10.0)
    reward = compute_reward(prev, curr, action=0)
    # niente delta su nessun'altra componente → solo happiness_bonus
    assert reward == pytest.approx(REWARD_WEIGHTS["happiness_bonus"], abs=1e-6)


def test_happiness_bonus_below_threshold() -> None:
    """happiness=3 (≤5) → contributo 0."""
    prev = _gs(happiness=3.0)
    curr = _gs(happiness=3.0)
    reward = compute_reward(prev, curr, action=0)
    assert reward == pytest.approx(0.0, abs=1e-6)


def test_happiness_bonus_cap_not_exceeded() -> None:
    """happiness=100 → bonus = 0.05 (mai oltre il cap)."""
    prev = _gs(happiness=100.0)
    curr = _gs(happiness=100.0)
    reward = compute_reward(prev, curr, action=0)
    assert reward == pytest.approx(REWARD_WEIGHTS["happiness_bonus"], abs=1e-6)


# --- Building diversity (una tantum) ------------------------------------------

def test_building_diversity_first_time() -> None:
    """Primo Library mai costruito su tutta la civ → +0.5."""
    prev = _gs(cities=[CityState("Rome", 3, "Monument", [], 200, 0)])
    curr = _gs(cities=[CityState("Rome", 3, "Monument", ["Library"], 200, 0)])
    reward = compute_reward(prev, curr, action=0)
    # contributo atteso = building_complete (1.5) + building_diversity (0.5) = 2.0
    expected_min = REWARD_WEIGHTS["building_complete"] + REWARD_WEIGHTS["building_diversity"]
    assert reward >= expected_min - 1e-6


def test_building_diversity_second_time() -> None:
    """Secondo Library in un'altra città → solo building_complete, no diversity."""
    prev = _gs(cities=[
        CityState("Rome", 3, "Monument", ["Library"], 200, 0),
        CityState("Delhi", 3, "", [], 200, 0),
    ])
    curr = _gs(cities=[
        CityState("Rome", 3, "Monument", ["Library"], 200, 0),
        CityState("Delhi", 3, "", ["Library"], 200, 0),
    ])
    reward = compute_reward(prev, curr, action=0)
    # building_complete (1.5) + cities_alive_bonus (0.05) ma NIENTE diversity
    expected = REWARD_WEIGHTS["building_complete"] + REWARD_WEIGHTS["cities_alive_bonus"]
    assert reward == pytest.approx(expected, abs=1e-6)


# --- Regression ----------------------------------------------------------------

# --- File 24 — city_connected_to_capital + road_built ------------------------


def _gs_with_roads(
    cities_connected_to_capital: int = 0,
    tiles_with_road: set | None = None,
) -> GameState:
    """Costruisce un GameState minimale per i test File 24 (campi nuovi post-construct)."""
    state = GameState(
        turn=10, current_player="India", gold=200, happiness=5,
        cities=[CityState("Rome", 3, "Monument", [], 200, 0)],
        techs_researched=["Agriculture"], current_tech="Writing",
        map_width=20, map_height=20,
    )
    state.cities_connected_to_capital = cities_connected_to_capital
    state.tiles_with_road = tiles_with_road if tiles_with_road is not None else set()
    return state


def test_city_connected_delta_positive() -> None:
    """Una città in più connessa alla capitale → reward include +city_connected_to_capital (4.0)."""
    prev = _gs_with_roads(cities_connected_to_capital=0)
    curr = _gs_with_roads(cities_connected_to_capital=1)
    reward = compute_reward(prev, curr, action=0)
    assert reward >= REWARD_WEIGHTS["city_connected_to_capital"] - 1e-6


def test_city_connected_no_delta() -> None:
    """Stesso numero di città connesse → contributo 0 da city_connected_to_capital."""
    prev = _gs_with_roads(cities_connected_to_capital=2)
    curr = _gs_with_roads(cities_connected_to_capital=2)
    reward = compute_reward(prev, curr, action=0)
    assert reward == pytest.approx(0.0, abs=1e-6)


def test_road_built_positive_delta() -> None:
    """Una road nuova costruita → reward include +road_built (0.3)."""
    prev = _gs_with_roads(tiles_with_road=set())
    curr = _gs_with_roads(tiles_with_road={(0, 0)})
    reward = compute_reward(prev, curr, action=0)
    assert reward >= REWARD_WEIGHTS["road_built"] - 1e-6


def test_road_built_no_delta() -> None:
    """tiles_with_road invariati → contributo 0 da road_built."""
    prev = _gs_with_roads(tiles_with_road={(1, 1), (2, 2)})
    curr = _gs_with_roads(tiles_with_road={(1, 1), (2, 2)})
    reward = compute_reward(prev, curr, action=0)
    assert reward == pytest.approx(0.0, abs=1e-6)


def test_regression_episode_bound() -> None:
    """150 turni con valori 'tipici' → total_reward < 500 (no esplosione)."""
    total = 0.0
    # Stato base
    techs = ["Agriculture"]
    prev = _gs(
        cities=[CityState("Rome", 3, "Monument", [], 200, 0)],
        techs=list(techs),
        science_per_turn=5.0,
        gold_per_turn=2.0,
        culture_per_turn=1.0,
        happiness=6.0,
        faith_per_turn=0.0,
        current_tech="Writing",
        current_tech_progress=0.0,
        current_tech_cost=55.0,
    )
    pop = 3
    science = 5.0
    gold_pt = 2.0
    culture_pt = 1.0
    faith_pt = 0.0
    progress = 0.0
    for t in range(150):
        # crescita lenta e plausibile
        if t % 20 == 0 and pop < 12:
            pop += 1
        if t % 10 == 0:
            science += 1.0
            gold_pt += 0.5
            culture_pt += 0.3
        progress = min(progress + science, 54.0)
        curr = _gs(
            turn=10 + t,
            cities=[CityState("Rome", pop, "Monument", ["Granary"] if t > 5 else [], 200, 0)],
            techs=list(techs),
            science_per_turn=science,
            gold_per_turn=gold_pt,
            culture_per_turn=culture_pt,
            happiness=6.0,
            faith_per_turn=faith_pt,
            current_tech="Writing",
            current_tech_progress=progress,
            current_tech_cost=55.0,
        )
        total += compute_reward(prev, curr, action=0)
        prev = curr
    assert total < 500.0, f"Esplosione reward: total={total}"
    assert total > -50.0, f"Reward troppo negativo per scenario tipico: total={total}"
