# NEXT GOAL DP POC

`next_goal_dp.py` is a small, standard-library-only prototype. It adapts the
Bellman formulation in Das, Ostrov, Radhakrishnan and Srivastav, *Dynamic
Optimization for Multi-Goals Wealth Management* (Journal of Banking & Finance,
2022) to cash-flow planning:

- the paper's wealth grid becomes a cash grid;
- the paper's portfolio return transition becomes dated income and bill events;
- the paper's goal set is represented as `none`, `half`, or `full` funding;
- essential bills and the minimum reserve are hard constraints;
- scenario probabilities are used in the Bellman expectation.

The paper and the exact extraction used for this adaptation are recorded in
[`DP_RESEARCH_NOTES.md`](DP_RESEARCH_NOTES.md). Franklin Templeton's GOE
description confirms the same high-level use of dynamic programming, but it does
not publish the product's implementation. This POC is therefore an independent
adaptation, not a reproduction of GOE.

The CLI also evaluates a deliberately simple comparator: save a fixed monthly
amount and greedily advance goals in the order supplied by the user. It uses the
same dated events, scenario probabilities, cash grid, and reserve constraint as
the DP. The comparator is a reference point for an experiment, not a claim that
one method wins for all users or assumptions.

## Run the demo

From the repository root:

```text
python NEW/next_goal_dp.py
python NEW/next_goal_dp.py --json
python NEW/next_goal_dp.py --fixed-saving 6000 --json
```

The demo compares a baseline with a candidate 4,500 THB transfer on month 1,
day 16. The unexpected-expense scenario makes that transfer fail the 2,000 THB
reserve constraint. The CLI also finds the largest grid-sized transfer that is
feasible under every configured scenario.

## JSON input

Pass a file with `--input path.json`. Amounts are in THB. Positive cash-flow
amounts are inflows and negative amounts are outflows. Scenario events are added
to the base events; probabilities must sum to one.

```json
{
  "initial_cash": 18000,
  "reserve_min": 2000,
  "grid_step": 500,
  "horizon_months": 3,
  "comfort_buffer": 4000,
  "cash_tightness_penalty": 0.002,
  "cashflows": [
    {"month": 1, "day": 1, "amount": -9000, "essential": true, "label": "rent"},
    {"month": 1, "day": 10, "amount": 16000, "label": "salary"}
  ],
  "scenarios": [
    {"name": "base", "probability": 0.8, "events": []},
    {
      "name": "unexpected expense",
      "probability": 0.2,
      "events": [
        {"month": 1, "day": 15, "amount": -2000, "essential": true, "label": "medical expense"}
      ]
    }
  ],
  "goals": [
    {
      "name": "emergency top-up",
      "target": 12000,
      "due_month": 2,
      "utility_half": 25,
      "utility_full": 60,
      "late_penalty": 5
    }
  ]
}
```

## Bellman recurrence

For state `s` at month `t`, action `a` allocates money to each goal. For every
scenario `ω`, dated events produce a next state `s'ω`. An action is discarded if
any scenario drops below the reserve during its events or after goal funding.
The remaining actions are scored as:

```text
V_t(s) = max_a [ Eω( goal_utility_t(a)
                    - cash_tightness_penalty_t(a,ω)
                    + V_(t+1)(s'ω) ) ]
```

The implementation stores the maximizing action as a policy for each reachable
`(t, state)`. A forward pass then follows that policy through all scenarios and
reports the final probability of each goal being at none/half/full. The
probability is conditional on the supplied scenario set and is not a forecast
guarantee.

## Tests

```text
python -m unittest discover -s NEW -p "test_*.py"
```

The tests cover the Bellman choice on a small problem, event-date liquidity,
reserved goal money, half-to-full funding, goal deferral, no-feasible-plan
handling, probability normalization, the fixed-rule comparator, and transfer
checks.

## Deliberate limits

This prototype does not connect to K PLUS, infer transaction categories, detect
scams, recommend securities, or estimate real-world probabilities. It uses a
conservative cash grid and requires the selected action to be feasible in every
configured scenario. Goal deferral and the 0/50/100% progress state are
extensions for NEXT GOAL; the paper fixes goal dates and does not automatically
move a missed goal to a later year.
