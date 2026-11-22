"""Показать зависимые оценки и сроки обязательств сохранённого дела."""

import argparse
from datetime import date
import sys
from pathlib import Path

from check import require_text
from score import evidence_ids, read_json


def report(folder, refs, today):
    ids = evidence_ids(folder / "evidence.md")
    if not set(refs) <= ids:
        raise ValueError("Некоторые ID отсутствуют в evidence.md.")
    lines = []
    if refs:
        sc = read_json(folder / "scoring.json")
        for oid, item in sc["assessments"].items():
            for field in ("criteria", "gates"):
                for key, record in item[field].items():
                    found = sorted(set(record.get("refs", [])) & set(refs))
                    if found:
                        lines.append(f"{oid} / {field} / {key} — {', '.join(found)}: {record['reason']}")
        if not lines:
            lines.append("Прямых ссылок в оценках нет. Проверьте новое основание по его смыслу.")
    file = folder / "commitments.json"
    if not file.exists():
        lines.append("Обязательства в деле пока не записаны.")
        return lines
    register = read_json(file)
    if not isinstance(register, dict) or not isinstance(register.get("items"), list):
        raise ValueError("Нужен список обязательств items.")
    dues, used = [], set()
    for entry in register["items"]:
        if not isinstance(entry, dict):
            raise ValueError("Обязательство должно быть объектом.")
        for k in ("id", "owner", "action", "metric", "review_if"):
            require_text(entry.get(k), k)
        if entry["id"] in used:
            raise ValueError("Повторяется ID обязательства.")
        used.add(entry["id"])
        status = entry.get("status")
        if status not in ("open", "done", "cancelled"):
            raise ValueError("Неизвестный статус обязательства.")
        er = entry.get("evidence")
        if not isinstance(er, list) or any(not isinstance(r, str) or r not in ids for r in er):
            raise ValueError("Проверьте источники обязательства.")
        value = entry.get("due")
        if value is not None and not isinstance(value, str):
            raise ValueError("Срок должен быть датой или null.")
        due = date.fromisoformat(value) if value else None
        if status != "open" or (refs and not set(er).intersection(refs)):
            continue
        if due is None:
            label = "уточнить срок"
        elif due < today:
            label = "просрочено"
        elif due == today:
            label = "сегодня"
        else:
            label = "предстоит"
        dues.append((due or date.max, entry["id"], f"{value or '—'} · {label} · {entry['owner']} — {entry['action']}. "
                     f"Показатель: {entry['metric']}. Пересмотр: {entry['review_if']}."))
    lines.extend(row[2] for row in sorted(dues))
    if not dues:
        lines.append("Открытых обязательств для этой выборки нет.")
    return lines


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("case", type=Path)
    p.add_argument("--evidence", nargs="*", default=[])
    p.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = p.parse_args()
    try:
        print("\n".join(report(args.case, args.evidence, args.as_of)))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"Проверка прервана — {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
