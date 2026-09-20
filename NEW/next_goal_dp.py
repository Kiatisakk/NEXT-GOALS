"""Small, inspectable stochastic dynamic-programming POC for NEXT GOAL.

The model follows the useful part of Das et al.'s goals-based formulation:
the optimizer chooses a set of goal actions at each time step and uses a
Bellman backward pass to value the consequences of today's choice.  The
portfolio return process from the paper is replaced with dated cash-flow
events, because this POC is about liquidity and saving rather than asset
allocation.

The command line demo uses synthetic data only.  It is not connected to K
PLUS, does not identify scams, and should not be used as financial advice.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass, replace
from functools import lru_cache
from itertools import product
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


EPSILON = 1e-9
LEVEL_NAMES = ("none", "half", "full")


@dataclass(frozen=True)
class Goal:
    """A savings goal whose progress is represented by 0%, 50%, or 100%."""

    name: str
    target: float
    due_month: int
    utility_half: float
    utility_full: float
    late_penalty: float = 0.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("goal name must not be empty")
        if self.target <= 0:
            raise ValueError("goal target must be positive")
        if self.due_month < 1:
            raise ValueError("goal due_month must be at least 1")
        if self.utility_half < 0 or self.utility_full < self.utility_half:
            raise ValueError(
                "utility_full must be >= utility_half >= 0"
            )
        if self.late_penalty < 0:
            raise ValueError("late_penalty must not be negative")


@dataclass(frozen=True)
class CashEvent:
    """A dated cash-flow event. Positive amounts are inflows."""

    month: int
    day: int
    amount: float
    essential: bool = False
    label: str = ""

    def __post_init__(self) -> None:
        if self.month < 1:
            raise ValueError("event month must be at least 1")
        if self.day < 1 or self.day > 31:
            raise ValueError("event day must be between 1 and 31")
        if not math.isfinite(self.amount):
            raise ValueError("event amount must be finite")


@dataclass(frozen=True)
class Scenario:
    """Scenario-specific cash-flow additions and their probability."""

    name: str
    probability: float
    events: tuple[CashEvent, ...] = ()

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("scenario name must not be empty")
        if self.probability <= 0 or not math.isfinite(self.probability):
            raise ValueError("scenario probability must be positive and finite")


@dataclass(frozen=True)
class Problem:
    """Inputs to the cash-flow goal-planning problem."""

    initial_cash: float
    reserve_min: float
    grid_step: float
    horizon_months: int
    goals: tuple[Goal, ...]
    base_events: tuple[CashEvent, ...] = ()
    scenarios: tuple[Scenario, ...] = ()
    comfort_buffer: float = 0.0
    cash_tightness_penalty: float = 0.0

    def __post_init__(self) -> None:
        if self.initial_cash < 0:
            raise ValueError("initial_cash must not be negative")
        if self.reserve_min < 0:
            raise ValueError("reserve_min must not be negative")
        if self.grid_step <= 0:
            raise ValueError("grid_step must be positive")
        if self.horizon_months < 1:
            raise ValueError("horizon_months must be at least 1")
        if len(self.goals) == 0:
            raise ValueError("at least one goal is required")
        if self.comfort_buffer < 0 or self.cash_tightness_penalty < 0:
            raise ValueError("comfort_buffer and cash_tightness_penalty must not be negative")
        for goal in self.goals:
            if goal.due_month > self.horizon_months:
                raise ValueError("goal due_month cannot exceed horizon_months")
        for event in self.base_events:
            if event.month > self.horizon_months:
                raise ValueError("base event month cannot exceed horizon_months")
        for scenario in self.scenarios:
            for event in scenario.events:
                if event.month > self.horizon_months:
                    raise ValueError("scenario event month cannot exceed horizon_months")
        if self.scenarios:
            total = sum(s.probability for s in self.scenarios)
            if not math.isclose(total, 1.0, rel_tol=1e-8, abs_tol=1e-8):
                raise ValueError("scenario probabilities must sum to 1")

    @property
    def normalized_scenarios(self) -> tuple[Scenario, ...]:
        if self.scenarios:
            return self.scenarios
        return (Scenario(name="base", probability=1.0),)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Problem":
        """Parse the intentionally small JSON format documented in README."""

        def parse_event(item: Mapping[str, Any]) -> CashEvent:
            return CashEvent(
                month=int(item["month"]),
                day=int(item.get("day", 1)),
                amount=float(item["amount"]),
                essential=bool(item.get("essential", False)),
                label=str(item.get("label", "")),
            )

        goals = tuple(
            Goal(
                name=str(item["name"]),
                target=float(item["target"]),
                due_month=int(item["due_month"]),
                utility_half=float(item["utility_half"]),
                utility_full=float(item["utility_full"]),
                late_penalty=float(item.get("late_penalty", 0.0)),
            )
            for item in raw["goals"]
        )
        scenarios = tuple(
            Scenario(
                name=str(item["name"]),
                probability=float(item["probability"]),
                events=tuple(parse_event(event) for event in item.get("events", ())),
            )
            for item in raw.get("scenarios", ())
        )
        return cls(
            initial_cash=float(raw["initial_cash"]),
            reserve_min=float(raw["reserve_min"]),
            grid_step=float(raw.get("grid_step", 500.0)),
            horizon_months=int(raw["horizon_months"]),
            goals=goals,
            base_events=tuple(parse_event(event) for event in raw.get("cashflows", ())),
            scenarios=scenarios,
            comfort_buffer=float(raw.get("comfort_buffer", 0.0)),
            cash_tightness_penalty=float(raw.get("cash_tightness_penalty", 0.0)),
        )


@dataclass(frozen=True)
class State:
    """A DP state; cash is conservatively rounded down to the grid."""

    cash: float
    progress: tuple[int, ...]


@dataclass(frozen=True)
class Action:
    """A joint action for all goals at one month."""

    allocations: tuple[float, ...]
    next_progress: tuple[int, ...]
    labels: tuple[str, ...]
    goal_reward: float

    @property
    def total_allocation(self) -> float:
        return sum(self.allocations)


@dataclass(frozen=True)
class ScenarioTransition:
    scenario: Scenario
    next_state: State
    cash_after_events: float
    cash_after_goals: float
    cash_tightness_penalty: float


@dataclass(frozen=True)
class Transition:
    action: Action
    outcomes: tuple[ScenarioTransition, ...]
    expected_immediate_reward: float


@dataclass
class ForwardReport:
    """Probability distribution produced by following the stored policy."""

    state_distribution_by_month: list[dict[State, float]]
    goal_level_probabilities: dict[str, dict[str, float]]
    expected_cash_by_month: list[float]


@dataclass
class SolveResult:
    problem: Problem
    feasible: bool
    value: float
    initial_state: State
    policy: dict[tuple[int, State], Action]
    values: dict[tuple[int, State], float]
    forward: ForwardReport | None
    failure_reason: str | None
    elapsed_ms: float

    def first_action(self) -> Action | None:
        return self.policy.get((1, self.initial_state))

    def summary(self) -> dict[str, Any]:
        first = self.first_action()
        result: dict[str, Any] = {
            "feasible": self.feasible,
            "value": None if not self.feasible else round(self.value, 6),
            "elapsed_ms": round(self.elapsed_ms, 6),
            "failure_reason": self.failure_reason,
        }
        if first is not None:
            result["first_action"] = {
                "allocations": {
                    goal.name: round(amount, 2)
                    for goal, amount in zip(self.problem.goals, first.allocations)
                },
                "next_levels": {
                    goal.name: LEVEL_NAMES[level]
                    for goal, level in zip(self.problem.goals, first.next_progress)
                },
                "labels": list(first.labels),
                "goal_reward": round(first.goal_reward, 6),
            }
        if self.forward is not None:
            result["goal_level_probabilities"] = self.forward.goal_level_probabilities
            result["expected_cash_by_month"] = [
                round(value, 2) for value in self.forward.expected_cash_by_month
            ]
        return result


@dataclass
class FixedRuleResult:
    """Outcome of a simple fixed monthly-saving rule used as a comparator."""

    feasible: bool
    monthly_saving: float
    goal_level_probabilities: dict[str, dict[str, float]] | None
    expected_cash_by_month: list[float]
    failure_reason: str | None

    def summary(self) -> dict[str, Any]:
        return {
            "feasible": self.feasible,
            "monthly_saving": round(self.monthly_saving, 2),
            "failure_reason": self.failure_reason,
            "goal_level_probabilities": self.goal_level_probabilities,
            "expected_cash_by_month": [round(value, 2) for value in self.expected_cash_by_month],
        }


def _quantize_down(value: float, step: float) -> float:
    """Round cash down so the grid never overstates liquidity."""

    return math.floor((value + EPSILON) / step) * step


class NextGoalDP:
    """Finite-horizon stochastic Bellman solver."""

    def __init__(self, problem: Problem):
        self.problem = problem
        self.scenarios = problem.normalized_scenarios
        self._policy: dict[tuple[int, State], Action] = {}
        self._values: dict[tuple[int, State], float] = {}
        self._failure_reasons: dict[tuple[int, State], str] = {}

    def initial_state(self) -> State:
        return State(
            cash=_quantize_down(self.problem.initial_cash, self.problem.grid_step),
            progress=(0,) * len(self.problem.goals),
        )

    def solve(self) -> SolveResult:
        started = time.perf_counter()
        initial = self.initial_state()

        @lru_cache(maxsize=None)
        def value(month: int, state: State) -> float:
            if month > self.problem.horizon_months:
                terminal = self._terminal_value(state)
                self._values[(month, state)] = terminal
                return terminal

            best_value = -math.inf
            best_transition: Transition | None = None
            first_failure: str | None = None
            for action in self._actions(state.progress, month):
                transition, reason = self._transition(month, state, action)
                if transition is None:
                    if first_failure is None:
                        first_failure = reason
                    continue
                continuation = sum(
                    outcome.scenario.probability
                    * value(month + 1, outcome.next_state)
                    for outcome in transition.outcomes
                )
                candidate = transition.expected_immediate_reward + continuation
                if candidate > best_value + EPSILON:
                    best_value = candidate
                    best_transition = transition

            self._values[(month, state)] = best_value
            if best_transition is not None:
                self._policy[(month, state)] = best_transition.action
            elif first_failure is not None:
                self._failure_reasons[(month, state)] = first_failure
            return best_value

        optimal_value = value(1, initial)
        feasible = math.isfinite(optimal_value)
        forward = self._forward_pass(initial) if feasible else None
        failure = None
        if not feasible:
            failure = self._failure_reasons.get(
                (1, initial),
                "no action satisfies the liquidity constraints for every scenario",
            )
        return SolveResult(
            problem=self.problem,
            feasible=feasible,
            value=optimal_value,
            initial_state=initial,
            policy=dict(self._policy),
            values=dict(self._values),
            forward=forward,
            failure_reason=failure,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )

    def _terminal_value(self, state: State) -> float:
        # Unfinished goals receive no utility. This mirrors the paper's use of
        # explicit goal utility while keeping the POC's objective transparent.
        return 0.0

    def _events_for(self, month: int, scenario: Scenario) -> tuple[CashEvent, ...]:
        events = [event for event in self.problem.base_events if event.month == month]
        events.extend(event for event in scenario.events if event.month == month)
        return tuple(sorted(events, key=lambda event: (event.day, event.label)))

    def _project_events(
        self, month: int, state: State, scenario: Scenario
    ) -> tuple[float | None, str | None]:
        cash = state.cash
        if cash < self.problem.reserve_min - EPSILON:
            return None, (
                f"starting cash {cash:.2f} is below reserve "
                f"{self.problem.reserve_min:.2f}"
            )
        for event in self._events_for(month, scenario):
            cash += event.amount
            if cash < self.problem.reserve_min - EPSILON:
                label = event.label or "unlabelled cash event"
                return None, (
                    f"scenario {scenario.name!r} falls below reserve after "
                    f"{label!r} on month {event.month}, day {event.day} "
                    f"({cash:.2f} < {self.problem.reserve_min:.2f})"
                )
        return cash, None

    def _goal_options(
        self, goal: Goal, current_level: int, month: int
    ) -> tuple[tuple[int, float, str, float], ...]:
        """Return (new level, allocation, label, incremental utility)."""

        if current_level == 2:
            return ((2, 0.0, "keep full", 0.0),)
        late = max(0, month - goal.due_month) * goal.late_penalty
        half_amount = goal.target / 2.0
        if current_level == 0:
            return (
                (0, 0.0, "defer", 0.0),
                (1, half_amount, "fund half", goal.utility_half - late),
                (2, goal.target, "fund full", goal.utility_full - late),
            )
        return (
            (1, 0.0, "keep half", 0.0),
            (2, half_amount, "complete full", goal.utility_full - goal.utility_half - late),
        )

    def _actions(
        self, progress: tuple[int, ...], month: int
    ) -> Iterable[Action]:
        options = [
            self._goal_options(goal, level, month)
            for goal, level in zip(self.problem.goals, progress)
        ]
        for choices in product(*options):
            next_progress = tuple(choice[0] for choice in choices)
            allocations = tuple(choice[1] for choice in choices)
            labels = tuple(choice[2] for choice in choices)
            goal_reward = sum(choice[3] for choice in choices)
            yield Action(
                allocations=allocations,
                next_progress=next_progress,
                labels=labels,
                goal_reward=goal_reward,
            )

    def _transition(
        self, month: int, state: State, action: Action
    ) -> tuple[Transition | None, str | None]:
        outcomes: list[ScenarioTransition] = []
        total_allocation = action.total_allocation
        for scenario in self.scenarios:
            cash_after_events, reason = self._project_events(month, state, scenario)
            if cash_after_events is None:
                return None, reason
            cash_after_goals = cash_after_events - total_allocation
            if cash_after_goals < self.problem.reserve_min - EPSILON:
                return None, (
                    f"action allocates {total_allocation:.2f} and leaves "
                    f"{cash_after_goals:.2f} below reserve "
                    f"{self.problem.reserve_min:.2f} in scenario {scenario.name!r}"
                )
            next_cash = _quantize_down(cash_after_goals, self.problem.grid_step)
            if next_cash < self.problem.reserve_min - EPSILON:
                return None, (
                    f"grid rounding leaves {next_cash:.2f} below reserve "
                    f"{self.problem.reserve_min:.2f} in scenario {scenario.name!r}"
                )
            tightness = max(
                0.0,
                self.problem.comfort_buffer
                - (cash_after_goals - self.problem.reserve_min),
            )
            outcomes.append(
                ScenarioTransition(
                    scenario=scenario,
                    next_state=State(next_cash, action.next_progress),
                    cash_after_events=cash_after_events,
                    cash_after_goals=cash_after_goals,
                    cash_tightness_penalty=tightness,
                )
            )

        expected_penalty = sum(
            outcome.scenario.probability
            * outcome.cash_tightness_penalty
            * self.problem.cash_tightness_penalty
            for outcome in outcomes
        )
        return (
            Transition(
                action=action,
                outcomes=tuple(outcomes),
                expected_immediate_reward=action.goal_reward - expected_penalty,
            ),
            None,
        )

    def _forward_pass(self, initial: State) -> ForwardReport:
        distribution: dict[State, float] = {initial: 1.0}
        distributions = [distribution]
        expected_cash = [initial.cash]
        for month in range(1, self.problem.horizon_months + 1):
            next_distribution: dict[State, float] = {}
            for state, state_probability in distribution.items():
                action = self._policy[(month, state)]
                transition, reason = self._transition(month, state, action)
                if transition is None:
                    raise RuntimeError(
                        f"stored policy became infeasible at month {month}: {reason}"
                    )
                for outcome in transition.outcomes:
                    probability = state_probability * outcome.scenario.probability
                    next_state = outcome.next_state
                    next_distribution[next_state] = (
                        next_distribution.get(next_state, 0.0) + probability
                    )
            distribution = next_distribution
            distributions.append(distribution)
            expected_cash.append(
                sum(state.cash * probability for state, probability in distribution.items())
            )
        level_mass: dict[str, dict[int, float]] = {
            goal.name: {0: 0.0, 1: 0.0, 2: 0.0}
            for goal in self.problem.goals
        }
        for state, probability in distribution.items():
            for index, goal in enumerate(self.problem.goals):
                level_mass[goal.name][state.progress[index]] += probability

        goal_probabilities = {
            name: {
                LEVEL_NAMES[level]: round(probability, 10)
                for level, probability in levels.items()
            }
            for name, levels in level_mass.items()
        }
        return ForwardReport(
            state_distribution_by_month=distributions,
            goal_level_probabilities=goal_probabilities,
            expected_cash_by_month=expected_cash,
        )


def with_transfer(
    problem: Problem,
    amount: float,
    month: int,
    day: int,
    label: str = "candidate transfer",
) -> Problem:
    """Return a copy with a candidate transfer inserted into base cash flows."""

    if amount < 0:
        raise ValueError("transfer amount must be non-negative")
    return replace(
        problem,
        base_events=problem.base_events
        + (CashEvent(month=month, day=day, amount=-amount, label=label),),
    )


def transfer_check(
    problem: Problem,
    amount: float,
    month: int,
    day: int,
    fixed_monthly_saving: float | None = None,
) -> dict[str, Any]:
    """Solve baseline and after-transfer plans and compare their summaries."""

    baseline = NextGoalDP(problem).solve()
    after_transfer = NextGoalDP(with_transfer(problem, amount, month, day)).solve()
    safe_limit = max_safe_transfer(problem, month, day)
    if fixed_monthly_saving is None:
        fixed_monthly_saving = default_fixed_monthly_saving(problem)
    fixed_rule = evaluate_fixed_rule(problem, fixed_monthly_saving)
    return {
        "transfer_amount": amount,
        "safe_transfer_limit": safe_limit,
        "baseline": baseline.summary(),
        "after_transfer": after_transfer.summary(),
        "fixed_rule": fixed_rule.summary(),
        "value_change": (
            None
            if not baseline.feasible or not after_transfer.feasible
            else round(after_transfer.value - baseline.value, 6)
        ),
    }


def default_fixed_monthly_saving(problem: Problem) -> float:
    """A transparent comparator default: the smallest half-goal amount."""

    half_goal = min(goal.target / 2.0 for goal in problem.goals)
    return max(problem.grid_step, _quantize_down(half_goal, problem.grid_step))


def _fixed_rule_action(
    solver: NextGoalDP,
    state: State,
    month: int,
    monthly_saving: float,
) -> Action:
    """Greedily fund goals in input order, capped by a fixed monthly budget."""

    remaining = monthly_saving
    desired = list(state.progress)
    for index, (goal, current_level) in enumerate(zip(solver.problem.goals, state.progress)):
        if current_level == 2:
            continue
        if current_level == 0:
            if remaining + EPSILON >= goal.target:
                desired[index] = 2
                remaining -= goal.target
            elif remaining + EPSILON >= goal.target / 2.0:
                desired[index] = 1
                remaining -= goal.target / 2.0
        elif remaining + EPSILON >= goal.target / 2.0:
            desired[index] = 2
            remaining -= goal.target / 2.0

    actions = [
        action
        for action in solver._actions(state.progress, month)
        if action.next_progress == tuple(desired)
    ]
    if not actions:
        raise RuntimeError("fixed rule generated an invalid goal action")
    return actions[0]


def evaluate_fixed_rule(problem: Problem, monthly_saving: float) -> FixedRuleResult:
    """Evaluate a fixed-budget, goal-priority rule through the same scenarios.

    This is deliberately a simple comparator, not a second optimizer. It uses
    the same dated events, grid, reserve constraint, and scenario probabilities
    as the DP, then greedily advances goals in the order supplied by the user.
    """

    if monthly_saving < 0:
        raise ValueError("monthly_saving must not be negative")
    solver = NextGoalDP(problem)
    initial = solver.initial_state()
    distribution: dict[State, float] = {initial: 1.0}
    expected_cash = [initial.cash]

    for month in range(1, problem.horizon_months + 1):
        next_distribution: dict[State, float] = {}
        for state, state_probability in distribution.items():
            proposed = _fixed_rule_action(solver, state, month, monthly_saving)
            transition, reason = solver._transition(month, state, proposed)
            if transition is None:
                # If the fixed target step is too large for the least-liquid
                # scenario, keep the goals unchanged but still test the cash
                # events and reserve rule.
                unchanged = next(
                    action
                    for action in solver._actions(state.progress, month)
                    if action.next_progress == state.progress
                )
                transition, reason = solver._transition(month, state, unchanged)
            if transition is None:
                return FixedRuleResult(
                    feasible=False,
                    monthly_saving=monthly_saving,
                    goal_level_probabilities=None,
                    expected_cash_by_month=expected_cash,
                    failure_reason=reason,
                )
            for outcome in transition.outcomes:
                probability = state_probability * outcome.scenario.probability
                next_state = outcome.next_state
                next_distribution[next_state] = (
                    next_distribution.get(next_state, 0.0) + probability
                )
        distribution = next_distribution
        expected_cash.append(
            sum(state.cash * probability for state, probability in distribution.items())
        )

    levels: dict[str, dict[str, float]] = {
        goal.name: {"none": 0.0, "half": 0.0, "full": 0.0}
        for goal in problem.goals
    }
    for state, probability in distribution.items():
        for index, goal in enumerate(problem.goals):
            levels[goal.name][LEVEL_NAMES[state.progress[index]]] += probability
    return FixedRuleResult(
        feasible=True,
        monthly_saving=monthly_saving,
        goal_level_probabilities={
            name: {level: round(probability, 10) for level, probability in values.items()}
            for name, values in levels.items()
        },
        expected_cash_by_month=expected_cash,
        failure_reason=None,
    )


def max_safe_transfer(
    problem: Problem,
    month: int,
    day: int,
    upper_bound: float | None = None,
) -> float | None:
    """Find the largest grid-sized transfer for which the DP remains feasible."""

    baseline = NextGoalDP(problem).solve()
    if not baseline.feasible:
        return None
    step = problem.grid_step
    if upper_bound is None:
        base_positive_cash = sum(max(event.amount, 0.0) for event in problem.base_events)
        scenario_positive_cash = max(
            (
                sum(max(event.amount, 0.0) for event in scenario.events)
                for scenario in problem.normalized_scenarios
            ),
            default=0.0,
        )
        positive_cash = base_positive_cash + scenario_positive_cash
        upper_bound = max(0.0, problem.initial_cash + positive_cash - problem.reserve_min)
    high = max(0, int(math.floor((upper_bound + EPSILON) / step)))
    low = 0
    while low < high:
        middle = (low + high + 1) // 2
        amount = middle * step
        candidate = NextGoalDP(with_transfer(problem, amount, month, day)).solve()
        if candidate.feasible:
            low = middle
        else:
            high = middle - 1
    return round(low * step, 2)


def demo_problem() -> Problem:
    """Synthetic scenario used by the CLI and README."""

    return Problem(
        initial_cash=18_000,
        reserve_min=2_000,
        grid_step=500,
        horizon_months=3,
        comfort_buffer=4_000,
        cash_tightness_penalty=0.002,
        base_events=(
            CashEvent(1, 1, -9_000, essential=True, label="rent"),
            CashEvent(1, 10, 16_000, label="salary"),
            CashEvent(1, 20, -17_000, essential=True, label="fixed bills"),
            CashEvent(2, 1, 16_000, label="salary"),
            CashEvent(2, 20, -10_000, essential=True, label="fixed bills"),
            CashEvent(3, 1, 16_000, label="salary"),
            CashEvent(3, 20, -10_000, essential=True, label="fixed bills"),
        ),
        scenarios=(
            Scenario("base", 0.8),
            Scenario(
                "unexpected expense",
                0.2,
                events=(CashEvent(1, 15, -2_000, essential=True, label="medical expense"),),
            ),
        ),
        goals=(
            Goal("emergency top-up", 12_000, 2, 25, 60, late_penalty=5),
            Goal("course fee", 20_000, 3, 20, 45, late_penalty=4),
        ),
    )


def _print_human_report(report: Mapping[str, Any]) -> None:
    print("NEXT GOAL — stochastic DP POC")
    print(f"safe transfer limit: {report.get('safe_transfer_limit')} THB")
    for label in ("baseline", "after_transfer"):
        summary = report[label]
        print(f"\n{label}: feasible={summary['feasible']}, value={summary['value']}")
        if summary.get("failure_reason"):
            print(f"  reason: {summary['failure_reason']}")
        if summary.get("first_action"):
            action = summary["first_action"]
            print(f"  first allocations: {action['allocations']}")
            print(f"  next levels: {action['next_levels']}")
        if summary.get("goal_level_probabilities"):
            print(f"  final goal levels: {summary['goal_level_probabilities']}")
        if summary.get("expected_cash_by_month"):
            print(f"  expected cash by month: {summary['expected_cash_by_month']}")
    fixed = report["fixed_rule"]
    print(
        f"\nfixed rule: {fixed['monthly_saving']} THB/month, "
        f"feasible={fixed['feasible']}"
    )
    if fixed.get("goal_level_probabilities"):
        print(f"  final goal levels: {fixed['goal_level_probabilities']}")
    print(f"\nvalue change: {report['value_change']}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="JSON problem file")
    parser.add_argument("--transfer", type=float, default=4_500)
    parser.add_argument("--transfer-month", type=int, default=1)
    parser.add_argument("--transfer-day", type=int, default=16)
    parser.add_argument(
        "--fixed-saving",
        type=float,
        help="fixed monthly-saving amount for the comparator (default: smallest half-goal)",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    if args.input:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        problem = Problem.from_dict(raw)
    else:
        problem = demo_problem()
    report = transfer_check(
        problem,
        amount=args.transfer,
        month=args.transfer_month,
        day=args.transfer_day,
        fixed_monthly_saving=args.fixed_saving,
    )
    if args.as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_human_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
