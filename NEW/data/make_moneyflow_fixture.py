"""Convert MoneyFlow's synthetic December 2024 statement to a DP smoke test."""

import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "moneyflow_sample_statement.csv"
OUTPUT = HERE / "moneyflow_dp_input.json"


def main() -> None:
    with SOURCE.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("source statement is empty")

    dates = [date.fromisoformat(row["Date"]) for row in rows]
    if dates != sorted(dates) or len({(d.year, d.month) for d in dates}) != 1:
        raise ValueError("this fixture expects one chronologically sorted month")

    opening = Decimal(rows[0]["Balance"]) - Decimal(rows[0]["Amount"])
    if opening < 0:
        raise ValueError("inferred opening balance is negative")

    cash = opening
    events = []
    for row, when in zip(rows, dates):
        amount = Decimal(row["Amount"])
        cash += amount
        if cash != Decimal(row["Balance"]):
            raise ValueError(f"balance does not reconcile on {when}")
        events.append(
            {
                "month": 1,
                "day": when.day,
                "amount": float(amount),
                "label": row["Description"],
            }
        )

    problem = {
        "initial_cash": float(opening),
        "reserve_min": 0,
        "grid_step": 10,
        "horizon_months": 1,
        "cashflows": events,
        "scenarios": [
            {"name": "statement_only", "probability": 0.8, "events": []},
            {
                "name": "assumed_extra_expense",
                "probability": 0.2,
                "events": [
                    {
                        "month": 1,
                        "day": 18,
                        "amount": -500,
                        "label": "assumed unexpected expense",
                    }
                ],
            },
        ],
        "goals": [
            {
                "name": "assumed_emergency_goal",
                "target": 1500,
                "due_month": 1,
                "utility_half": 25,
                "utility_full": 60,
            },
            {
                "name": "assumed_course_goal",
                "target": 1000,
                "due_month": 1,
                "utility_half": 15,
                "utility_full": 40,
            },
        ],
    }
    OUTPUT.write_text(json.dumps(problem, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} from {len(events)} transactions; opening={opening}, closing={cash}")


if __name__ == "__main__":
    main()
