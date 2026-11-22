"""Воспроизвести пересмотр рекомендации по недельному потоку пригодных клиентов."""

import argparse
import csv
from datetime import date
from pathlib import Path


PILOTS = {"family_signal": "семьи", "own_reminder": "владельцы своих номеров"}
STEPS = ("first_risk", "permitted", "actionable", "in_time")


def read_weeks(path):
    weeks = {}
    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if not {"week_start", "pilot", *STEPS}.issubset(reader.fieldnames or ()):
            raise ValueError("Нужны week_start, pilot и четыре ступени отбора.")
        for row in reader:
            week = date.fromisoformat(row["week_start"])
            pilot = row["pilot"]
            cohort = weeks.setdefault(week, {})
            if week.weekday() != 0 or pilot not in PILOTS or pilot in cohort:
                raise ValueError(f"Строка {reader.line_num}: проверьте начало недели и уникальность пилота.")
            counts = [int(row[key]) for key in STEPS]
            if min(counts) < 0 or counts != sorted(counts, reverse=True):
                raise ValueError(f"Строка {reader.line_num}: проверьте вложенность ступеней отбора.")
            cohort[pilot] = counts
    if not weeks or any(cohort.keys() != PILOTS.keys() for cohort in weeks.values()):
        raise ValueError("В каждой неделе нужны оба пилота.")
    return weeks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).with_name("weekly.synthetic.csv"))
    parser.add_argument("--sample", type=int, default=160, help="Суммарная выборка двух плеч одного пилота.")
    parser.add_argument("--weeks", type=int, default=4, help="Полные недели, доступные для набора.")
    args = parser.parse_args()
    if min(args.sample, args.weeks) <= 0:
        parser.error("Выборка и число недель должны быть положительными.")
    try:
        weeks = read_weeks(args.input)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    threshold = (args.sample + args.weeks - 1) // args.weeks
    print("# Результат учебного прогона\n")
    print(f"План набора — {args.sample} единиц за {args.weeks} нед. Порог — {threshold} в неделю.\n")
    print("| Неделя с | Пилот | С риском → с правами → есть действие → успевают | Запас к порогу |")
    print("| --- | --- | --- | ---: |")
    conclusions = []
    for week, cohort in sorted(weeks.items()):
        passed = []
        for pilot, label in PILOTS.items():
            counts = cohort[pilot]
            margin = counts[-1] - threshold
            print(f"| {week} | {label} | {' → '.join(map(str, counts))} | {margin:+d} |")
            if margin >= 0:
                passed.append(label)
        if len(passed) == 1:
            conclusion = f"Вынести на обсуждение пилот для сегмента «{passed[0]}»."
        elif passed:
            conclusion = "Оба пилота проходят по потоку. Сравнить ресурсы и ожидаемую пользу."
        else:
            conclusion = "Оба пилота ниже порога. Обсудить дополнительное наблюдение или обычное обслуживание."
        conclusions.append(f"- Неделя с {week}. {conclusion}")
    print("\n" + "\n".join(conclusions))
    print("\n**Вопрос руководителю.** Какой вариант вы выбираете после последнего среза и почему? "
          "Финансирование ожидает вашего решения.")


if __name__ == "__main__":
    main()
