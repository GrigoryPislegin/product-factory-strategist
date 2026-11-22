"""План двухгруппового испытания для бинарного исхода при равном распределении."""

import argparse
import math
from statistics import NormalDist


def per_arm(control_risk, reduction, alpha, power):
    """Нормальная аппроксимация для двух независимых долей, двусторонний тест."""
    treatment_risk = control_risk - reduction
    if not 0 < treatment_risk < control_risk < 1:
        raise ValueError("Нужно 0 < снижение < базовый риск < 100%.")
    if not 0 < alpha < 1 or not 0.5 < power < 1:
        raise ValueError("Проверьте уровень значимости и мощность.")
    avg = (control_risk + treatment_risk) / 2
    critical = -NormalDist().inv_cdf(alpha / 2)
    target = NormalDist().inv_cdf(power)
    null_sd = math.sqrt(2 * avg * (1 - avg))
    alt_sd = math.sqrt(control_risk * (1 - control_risk) + treatment_risk * (1 - treatment_risk))
    return math.ceil(((critical * null_sd + target * alt_sd) / reduction) ** 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--risks", type=float, nargs="+", default=[10, 20], help="Базовые риски в процентах.")
    parser.add_argument("--effects", type=float, nargs="+", default=[2, 5], help="Абсолютное снижение в п.п.")
    parser.add_argument("--per-week", type=int, default=40, help="Рандомизированных единиц в неделю на оба плеча одного пилота.")
    parser.add_argument("--weeks", type=int, default=4, help="Чистые недели набора в плане комитета.")
    parser.add_argument("--comparisons", type=int, choices=[1, 2], default=2, help="Число подтверждающих сравнений.")
    parser.add_argument("--power", type=float, default=0.8, help="Целевая мощность одного сравнения, доля.")
    args = parser.parse_args()
    if min(args.per_week, args.weeks) <= 0:
        parser.error("Поток и число недель должны быть положительными.")

    alpha = 0.05 / args.comparisons
    print(f"Сценарии. Двустороннее α на сравнение {alpha:g}. Мощность на сравнение {args.power:.0%}.\n")
    print("| Риск в контроле | Снижение | Риск с сигналом | На плечо | Всего на пилот | "
          f"Недель при {args.per_week}/нед. | Нужно в неделю за {args.weeks} нед. |")
    print("| ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for risk in args.risks:
        for effect in args.effects:
            try:
                n = per_arm(risk / 100, effect / 100, alpha, args.power)
            except ValueError as error:
                parser.error(str(error))
            total = 2 * n
            print(f"| {risk:g}% | {effect:g} п.п. | {risk-effect:g}% | {n} | {total} | "
                  f"{math.ceil(total / args.per_week)} | {math.ceil(total / args.weeks)} |")


if __name__ == "__main__":
    main()
