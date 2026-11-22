"""Границы разности рисков при неизвестных исходах в двух группах."""

import argparse
from fractions import Fraction


def risk_bounds(assigned, restricted, unknown):
    if assigned <= 0:
        raise ValueError("Для расчёта в каждом плече нужна хотя бы одна включённая единица.")
    if min(restricted, unknown) < 0 or restricted + unknown > assigned:
        raise ValueError("Ограничения и неизвестные исходы должны быть непересекающимися частями знаменателя.")
    return Fraction(restricted, assigned), Fraction(restricted + unknown, assigned)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arm in ("control", "pilot"):
        parser.add_argument(
            f"--{arm}", required=True, type=int, nargs=3,
            metavar=("ВСЕ", "ОГРАНИЧЕНЫ", "ИСХОД_НЕИЗВЕСТЕН"),
        )
    args = parser.parse_args()
    try:
        control_low, control_high = risk_bounds(*args.control)
        pilot_low, pilot_high = risk_bounds(*args.pilot)
    except ValueError as error:
        parser.error(str(error))

    low = 100 * (control_low - pilot_high)
    high = 100 * (control_high - pilot_low)
    print(f"Разность рисков (обычное обслуживание минус сигнал): "
          f"[{float(low):+.2f}, {float(high):+.2f}] п.п.")
    if low < 0 < high:
        print("В пределах пропусков возможны как снижение, так и рост риска.")
    elif low <= 0 <= high:
        print("Нулевой эффект совместим с наблюдаемыми исходами.")
    elif low > 0:
        print("При любом заполнении пропусков риск в наблюдаемой группе сигнала ниже.")
    else:
        print("При любом заполнении пропусков риск в наблюдаемой группе сигнала выше.")


if __name__ == "__main__":
    main()
