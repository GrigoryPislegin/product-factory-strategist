"""Оценка расхода одного сеанса. В сыром журнале читаются только turn.completed."""

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

COUNTERS = ("input_tokens", "cached_input_tokens", "output_tokens")


def token_number(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} должно быть неотрицательным целым числом.")
    return value


def parse_codex(stream):
    totals = dict.fromkeys(COUNTERS, 0)
    unknown_cached = False
    turns = 0
    for line in stream:
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict) or event.get("type") != "turn.completed":
            continue
        usage = event.get("usage")
        if not isinstance(usage, dict):
            raise ValueError("Завершённый ход не содержит usage.")
        for k in COUNTERS:
            if k == "cached_input_tokens" and usage.get(k) is None:
                unknown_cached = True
                continue
            totals[k] += token_number(usage.get(k), k)
        if usage.get("cached_input_tokens", 0) is not None and usage.get("cached_input_tokens", 0) > usage["input_tokens"]:
            raise ValueError("Кэшированные токены входят во входные.")
        turns += 1
    if not turns:
        raise ValueError("Нет завершённых ходов с расходом. Для единственного известного итога используйте --total.")
    if unknown_cached:
        totals["cached_input_tokens"] = None
    return {"completed_turns": turns, **totals, "total_tokens": totals["input_tokens"] + totals["output_tokens"]}


def price(value):
    amount = Decimal(value)
    if not amount.is_finite() or amount < 0:
        raise ValueError("Тариф должен быть конечным и неотрицательным.")
    return amount


def estimate(usage, rates):
    incoming = usage.get("input_tokens")
    outgoing = usage.get("output_tokens")
    cached = usage.get("cached_input_tokens")
    if incoming is None or outgoing is None or cached is None:
        raise ValueError("Для расчёта по тарифу нужны входные, кэшированные и выходные токены.")
    return ((incoming - cached) * rates[0] + cached * rates[1] + outgoing * rates[2]) / Decimal(1_000_000)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--codex-log", type=Path)
    group.add_argument("--total", type=int, help="только общий итог, если детализация отсутствует")
    parser.add_argument("--rates", nargs=3, metavar=("INPUT", "CACHE", "OUTPUT"), help="USD за 1 млн соответствующих токенов")
    args = parser.parse_args()
    try:
        if args.codex_log:
            with args.codex_log.open(encoding="utf-8") as f:
                usage = parse_codex(f)
        else:
            usage = {"total_tokens": token_number(args.total, "total")}
        if args.rates:
            usage["estimated_model_usd"] = str(estimate(usage, [price(n) for n in args.rates]))
        print(json.dumps(usage, indent=2))
    except (OSError, ValueError, InvalidOperation) as error:
        print(f"Расчёт прерван — {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
