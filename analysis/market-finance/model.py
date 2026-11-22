"""Порог годовой цели и прогноз по первым уникальным случаям без внешних библиотек."""

import argparse
import csv
import sys
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = HERE.parents[1] / "demo/family/baseline.csv"
MONTH_RUB = Decimal("500")
WEEKS = 13


def number(value, label, signed=False):
    amount = Decimal(value)
    if not amount.is_finite() or (amount < 0 and not signed):
        raise ValueError(f"Недопустимое число для {label}.")
    return amount


def required_months(gap_rub, direct, other):
    return (max(Decimal(0), gap_rub + direct - other) / MONTH_RUB).to_integral_value(rounding=ROUND_CEILING)


def forecast(row, gap_rub):
    inputs = {key: number(value, key, signed=key in ("months_q0", "months_q1", "months_q2")) for key, value in row.items() if key not in ("path", "scenario")}
    for key in ("first_risk_share_week", "eligible_share", "coverage_share"):
        if inputs[key] > 1:
            raise ValueError(f"{key} должен быть долей от 0 до 1.")
    if inputs["first_risk_share_week"] * WEEKS * 3 > 1:
        raise ValueError("Годовой набор первых случаев превысил доступную базу.")
    increments = [inputs[f"months_q{lag}"] for lag in range(3)]
    if any(abs(delta) > 3 for delta in increments):
        raise ValueError("Для одного целевого номера в квартале доступны до трёх месяцев по модулю.")
    weekly_eligible = inputs["reachable_units"] * inputs["first_risk_share_week"] * inputs["eligible_share"]
    enrolled = weekly_eligible * inputs["coverage_share"] * WEEKS
    quarters = []
    cumulative = Decimal(0)
    for q in range(1, 5):
        months = enrolled * sum(increments[:q-1])
        direct = inputs["annual_direct_rub"] / 3 if q >= 2 else Decimal(0)
        operating = months * MONTH_RUB - direct
        development = inputs["development_q2_rub"] if q == 2 else Decimal(0)
        cumulative += operating - development
        quarters.append((months, operating, development, cumulative))
    return weekly_eligible, required_months(gap_rub, inputs["annual_direct_rub"], 0), quarters


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scenarios", type=Path, default=HERE / "scenarios.csv")
    p.add_argument("--direct", default="0", help="новые прямые расходы в отдельной проверке порога, ₽")
    p.add_argument("--other", default="0", help="прочий дополнительный вклад в этой проверке, ₽")
    args = p.parse_args()
    try:
        with BASELINE.open(encoding="utf-8-sig", newline="") as stream:
            profit = next(r for r in csv.DictReader(stream) if r["metric"] == "Валовая прибыль за год")
        base = number(profit["next_year_status_quo"], "база") * 1_000_000
        target = number(profit["next_year_min_target"], "цель") * 1_000_000
        gap = target - base
        print(f"Разрыв {gap:,.0f} ₽. Порог при введённых расходах и прочем вкладе: "
              f"{required_months(gap, number(args.direct, 'direct'), number(args.other, 'other', signed=True)):,} номеро-месяцев.")
        with args.scenarios.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if not rows:
            raise ValueError("В таблице сценариев нет данных.")
        for row in rows:
            weekly, threshold, quarters = forecast(row, gap)
            print(f"\n{row['path']} / {row['scenario']} — {weekly:,.2f} пригодных единиц в неделю, годовой порог {threshold:,} мес.")
            print("квартал | дополнительные месяцы | вклад после прямых расходов ₽ | разработка ₽ | накоплено после разработки ₽")
            for quarter, values in enumerate(quarters, 1):
                print(quarter, *[f"{n:,.2f}" for n in values], sep=" | ")
            operating = sum(q[1] for q in quarters)
            total_months = sum(q[0] for q in quarters)
            print(f"Год: {total_months:,.2f} мес.; валовая прибыль {base + operating:,.2f} ₽; "
                  f"до цели {target - base - operating:,.2f} ₽ (отрицательное значение означает превышение).")
    except (ValueError, KeyError, OSError, InvalidOperation, StopIteration, TypeError) as error:
        print(f"Ошибка модели: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
