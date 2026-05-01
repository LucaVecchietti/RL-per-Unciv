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


def test_return_type_float():
    prev = make_state()
    curr = make_state()
    reward = compute_reward(prev, curr, action=0)
    assert isinstance(reward, float)
