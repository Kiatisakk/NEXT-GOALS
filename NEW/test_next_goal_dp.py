import unittest

from next_goal_dp import (
    CashEvent,
    Goal,
    NextGoalDP,
    Problem,
    Scenario,
    demo_problem,
    evaluate_fixed_rule,
    transfer_check,
)


def one_goal_problem(
    *,
    initial_cash=10_000,
    reserve_min=0,
    horizon_months=1,
    target=5_000,
    due_month=1,
    utility_half=1,
    utility_full=10,
    late_penalty=0,
    base_events=(),
    scenarios=(),
):
    return Problem(
        initial_cash=initial_cash,
        reserve_min=reserve_min,
        grid_step=500,
        horizon_months=horizon_months,
        base_events=tuple(base_events),
        scenarios=tuple(scenarios),
        goals=(
            Goal(
                "goal",
                target,
                due_month,
                utility_half,
                utility_full,
                late_penalty,
            ),
        ),
    )


class NextGoalDPTests(unittest.TestCase):
    def test_bellman_prefers_full_goal_when_it_has_more_utility(self):
        result = NextGoalDP(one_goal_problem()).solve()

        self.assertTrue(result.feasible)
        self.assertEqual(result.first_action().allocations, (5_000.0,))
        self.assertEqual(result.first_action().next_progress, (2,))
        self.assertEqual(result.value, 10)

    def test_event_date_constraint_is_checked_before_later_income(self):
        problem = one_goal_problem(
            initial_cash=5_000,
            reserve_min=2_000,
            base_events=(
                CashEvent(1, 1, -3_500, essential=True, label="rent"),
                CashEvent(1, 10, 5_000, label="salary"),
            ),
        )

        result = NextGoalDP(problem).solve()

        self.assertFalse(result.feasible)
        self.assertIn("rent", result.failure_reason)

    def test_goal_funding_is_removed_from_future_spendable_cash(self):
        result = NextGoalDP(
            one_goal_problem(initial_cash=10_000, reserve_min=2_000, target=8_000)
        ).solve()

        self.assertTrue(result.feasible)
        self.assertEqual(result.first_action().allocations, (8_000.0,))
        self.assertEqual(result.forward.expected_cash_by_month, [10_000, 2_000.0])

    def test_half_then_full_is_a_valid_two_step_path(self):
        problem = one_goal_problem(
            initial_cash=5_000,
            reserve_min=0,
            horizon_months=2,
            target=4_000,
            due_month=2,
            utility_half=5,
            utility_full=10,
        )
        solver = NextGoalDP(problem)
        initial = solver.initial_state()
        half = next(action for action in solver._actions((0,), 1) if action.next_progress == (1,))
        half_transition, _ = solver._transition(1, initial, half)
        self.assertIsNotNone(half_transition)
        half_state = half_transition.outcomes[0].next_state
        full = next(action for action in solver._actions(half_state.progress, 2) if action.next_progress == (2,))
        full_transition, _ = solver._transition(2, half_state, full)

        self.assertIsNotNone(full_transition)
        self.assertEqual(full.allocations, (2_000.0,))
        self.assertEqual(full_transition.outcomes[0].next_state.progress, (2,))

    def test_goal_can_be_deferred_until_income_arrives(self):
        result = NextGoalDP(
            one_goal_problem(
                initial_cash=5_000,
                reserve_min=0,
                horizon_months=2,
                target=4_000,
                due_month=1,
                base_events=(
                    CashEvent(1, 1, -4_000, essential=True, label="bill"),
                    CashEvent(2, 1, 4_000, label="salary"),
                ),
            )
        ).solve()

        self.assertTrue(result.feasible)
        self.assertEqual(result.first_action().allocations, (0.0,))
        self.assertEqual(result.first_action().labels, ("defer",))
        self.assertEqual(result.forward.goal_level_probabilities["goal"]["full"], 1.0)

    def test_no_feasible_plan_is_reported(self):
        problem = one_goal_problem(
            initial_cash=1_000,
            reserve_min=2_000,
            base_events=(CashEvent(1, 1, 10_000, label="salary"),),
        )

        result = NextGoalDP(problem).solve()

        self.assertFalse(result.feasible)
        self.assertIn("below reserve", result.failure_reason)

    def test_forward_probabilities_sum_to_one(self):
        problem = one_goal_problem(
            initial_cash=6_000,
            reserve_min=0,
            target=4_000,
            scenarios=(
                Scenario("base", 0.75),
                Scenario("shock", 0.25, (CashEvent(1, 15, -1_000, label="shock"),)),
            ),
        )
        result = NextGoalDP(problem).solve()

        self.assertTrue(result.feasible)
        probabilities = result.forward.goal_level_probabilities["goal"]
        self.assertAlmostEqual(sum(probabilities.values()), 1.0)

    def test_demo_transfer_check_finds_liquidity_failure(self):
        report = transfer_check(demo_problem(), 4_500, 1, 16)

        self.assertTrue(report["baseline"]["feasible"])
        self.assertFalse(report["after_transfer"]["feasible"])
        self.assertEqual(report["safe_transfer_limit"], 4_000.0)

    def test_fixed_rule_comparator_uses_the_same_scenarios(self):
        result = evaluate_fixed_rule(demo_problem(), 6_000)

        self.assertTrue(result.feasible)
        levels = result.goal_level_probabilities["emergency top-up"]
        self.assertAlmostEqual(sum(levels.values()), 1.0)
        self.assertEqual(levels["full"], 1.0)


if __name__ == "__main__":
    unittest.main()
