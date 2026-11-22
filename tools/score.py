"""Рассчитать сравнительную карту стратегий из файлов дела (Python 3, стандартная библиотека)."""

import argparse
import json
import re
import sys
from pathlib import Path

from check import read_state, require_alternatives, require_text


DEFAULT_RUBRIC = Path(__file__).resolve().parents[1] / "methods" / "decision-rubric.json"
GATE_LABELS = {"pass": "выполнено", "na": "не требуется", "pending": "проверить", "fail": "нарушено"}
BASIS_LABELS = {"evidence": "из источника", "assumption": "допущение", "unknown": "пробел"}
ELIGIBILITY = {"clear": "условия соблюдены", "pending": "есть открытое условие", "blocked": "условие нарушено"}
EVIDENCE_LINE = re.compile(r"^\s*(?:\|\s*(E[1-9]\d*)\s*\||[-*]\s+\*\*(E[1-9]\d*)(?=[,.:*]))")


def object_of(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Повторяется ключ {key}.")
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=object_of)


def mapping(value, field):
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{field} — нужен непустой объект.")
    return value


def same_keys(value, expected, field):
    mapping(value, field)
    if set(value) != set(expected):
        raise ValueError(f"{field} — ожидаются ключи {', '.join(expected)}.")


def validate_rubric(rubric):
    mapping(rubric, "rubric")
    require_text(rubric.get("version"), "rubric.version")
    criteria = mapping(rubric.get("criteria"), "criteria")
    for key, item in criteria.items():
        mapping(item, key)
        require_text(item.get("label"), key)
        scale = item.get("scale")
        if not isinstance(scale, list) or len(scale) != 5:
            raise ValueError(f"{key} — нужны ориентиры для баллов 0–4.")
        for anchor in scale:
            require_text(anchor, key)
    for name, weights in mapping(rubric.get("profiles"), "profiles").items():
        same_keys(weights, criteria, name)
        if any(type(w) is not int or w < 0 for w in weights.values()) or sum(weights.values()) != 100:
            raise ValueError(f"{name} — нужны целые неотрицательные веса с суммой 100.")


def evidence_ids(path):
    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = EVIDENCE_LINE.match(line)
        if match:
            key = match.group(1) or match.group(2)
            if key in ids:
                raise ValueError(f"В реестре два определения {key}.")
            ids.add(key)
    return ids


def rationale(item, ids, label, required):
    require_text(item.get("reason"), label + ".reason")
    refs = item.get("refs")
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        raise ValueError(f"{label} — refs должен быть списком строк.")
    unknown = sorted(set(refs) - ids)
    if unknown:
        raise ValueError(f"{label} — в evidence.md нет {', '.join(unknown)}. "
                         f"Определены: {', '.join(sorted(ids)) or 'нет ID'}.")
    if required and not refs:
        raise ValueError(f"{label} — укажите основание из evidence.md.")


def bounds(item, ids, label):
    mapping(item, label)
    basis = item.get("basis")
    if not isinstance(basis, str) or basis not in BASIS_LABELS or "band" not in item:
        raise ValueError(f"{label} — нужны basis и band.")
    rationale(item, ids, label, required=basis != "unknown")
    band = item["band"]
    if basis == "unknown":
        if band is not None:
            raise ValueError(f"{label} — при пробеле используйте null.")
        return 0, 4
    if (not isinstance(band, list) or len(band) != 2
            or any(type(n) is not int for n in band) or not 0 <= band[0] <= band[1] <= 4):
        raise ValueError(f"{label} — нужен диапазон двух целых от 0 до 4.")
    return tuple(band)


def assemble(state, case, rubric, ids):
    require_alternatives(state["options"])
    validate_rubric(rubric)
    mapping(case, "scoring")
    if case.get("rubric_version") != rubric["version"]:
        raise ValueError("Версии шкалы в деле и методике различаются.")
    require_text(case.get("horizon"), "horizon")
    require_text(case.get("next_evidence"), "next_evidence")
    criteria = rubric["criteria"]
    same_keys(case.get("measures"), criteria, "measures")
    for key, description in case["measures"].items():
        require_text(description, key)
    gates = mapping(case.get("gates"), "gates")
    for key, description in gates.items():
        require_text(description, key)
    assessments = case.get("assessments")
    same_keys(assessments, [o["id"] for o in state["options"]], "assessments")
    rows = {}
    for option in state["options"]:
        oid = option["id"]
        item = mapping(assessments[oid], oid)
        require_text(item.get("strength"), oid + ".strength")
        same_keys(item.get("criteria"), criteria, oid + ".criteria")
        bands = {key: bounds(item["criteria"][key], ids, f"{oid}.{key}") for key in criteria}
        same_keys(item.get("gates"), gates, oid + ".gates")
        statuses = set()
        for key, gate in item["gates"].items():
            mapping(gate, key)
            status = gate.get("status")
            if not isinstance(status, str) or status not in GATE_LABELS:
                raise ValueError(f"{oid}.{key} — неизвестное состояние условия.")
            rationale(gate, ids, f"{oid}.{key}", required=status != "pending")
            statuses.add(status)
        eligibility = "blocked" if "fail" in statuses else "pending" if "pending" in statuses else "clear"
        rows[oid] = {"bands": bands, "eligibility": eligibility}
    return rows


def compare(rows, weights):
    # Храним четверти балла целыми до вывода итогов.
    totals = {oid: tuple(sum(weights[k] * band[end] for k, band in row["bands"].items())
                         for end in (0, 1)) for oid, row in rows.items()}
    possible = [oid for oid, row in rows.items() if row["eligibility"] != "blocked"]
    for oid in possible:
        if rows[oid]["eligibility"] == "clear" and all(
            totals[oid][0] > totals[other][1] for other in possible if other != oid
        ):
            return totals, oid
    return totals, None


def display_score(quarter_points):
    """Середина границ в шкале 0–100 с округлением половин вверх."""
    return (sum(quarter_points) + 4) // 8


def span(pair, divisor=1):
    low, high = (format(n / divisor, "g").replace(".", ",") for n in pair)
    return low if low == high else f"{low}–{high}"


def note(record):
    return record["reason"] + (" (" + ", ".join(record["refs"]) + ")" if record["refs"] else "")


def cell(text):
    return text.replace("|", r"\|").replace("\n", " ")


def make_report(state, case, rubric, rows):
    options = state["options"]
    titles = {o["id"]: o["title"] for o in options}
    criteria = rubric["criteria"]
    profiles = rubric["profiles"]
    base = next(iter(profiles))
    comparisons = {name: compare(rows, weights) for name, weights in profiles.items()}
    winners = {winner for _, winner in comparisons.values()}
    robust = next(iter(winners)) if len(winners) == 1 else None
    conclusion = (f"Во всех профилях лидирует «{titles[robust]}»." if robust else
                  "Единственного лидера, устойчивого ко всем заданным весам и диапазонам, нет.")
    lines = ["# Сравнение стратегий", "", state["question"], "", case["horizon"], "", conclusion,
             "Выбор и основание решения фиксирует руководитель.", "", "**Что уточнить.** " + case["next_evidence"],
             "", "## Баллы из 100", ""]
    header = ["Вариант", "Обязательные условия", *profiles]
    lines.extend(["| " + " | ".join(map(cell, header)) + " |", "| " + " | ".join(["---"] * len(header)) + " |"])
    for oid, title in titles.items():
        values = [span(totals[oid], 4) for totals, _ in comparisons.values()]
        lines.append("| " + " | ".join(map(cell, [title, ELIGIBILITY[rows[oid]["eligibility"]], *values])) + " |")
    lines.extend(["", "Баллы в интервале зависят от указанных допущений и пробелов. Границы не задают вероятность.", ""])
    for profile, (_, winner) in comparisons.items():
        weights = ", ".join(f"{criteria[k]['label']} {v}%" for k, v in profiles[profile].items())
        result = f"лидирует «{titles[winner]}»" if winner else "лидер не установлен"
        lines.append(f"- {profile} ({weights}) — {result}.")
    lines.extend(["", "## Что оцениваем", ""])
    for key, item in criteria.items():
        lines.append(f"- **{item['label']}** — {case['measures'][key]}")
    for option in options:
        oid = option["id"]
        item = case["assessments"][oid]
        lines.extend(["", f"## {option['title']}", "", f"**Сильная сторона.** {item['strength']}",
                      "", f"**Сильнейшее возражение.** {option['objection']}", "",
                      f"Вклад в итог при профиле «{base}».", "",
                      "| Критерий | Балл из 4 | Вклад из 100 | Основание |",
                      "| --- | --- | --- | --- |"])
        for key, definition in criteria.items():
            record = item["criteria"][key]
            band = rows[oid]["bands"][key]
            contribution = span([n * profiles[base][key] for n in band], 4)
            descr = BASIS_LABELS[record["basis"]] + " — " + note(record)
            lines.append("| " + " | ".join(map(cell, [definition["label"], span(band), contribution, descr])) + " |")
        lines.append("")
        for key, gate in item["gates"].items():
            lines.append(f"- {case['gates'][key]} — **{GATE_LABELS[gate['status']]}**. {note(gate)}")
    return "\n".join(lines) + "\n"


def blank_assessment(state, rubric):
    validate_rubric(rubric)
    if not state["options"]:
        raise ValueError("Сначала запишите варианты в state.json.")
    criteria = rubric["criteria"]
    return {
        "rubric_version": rubric["version"], "horizon": "", "next_evidence": "",
        "measures": {key: "" for key in criteria},
        "gates": {"permitted": "Допустимость выбранного действия для этой аудитории"},
        "assessments": {o["id"]: {
            "strength": "",
            "criteria": {key: {"band": None, "basis": "unknown", "reason": "", "refs": []} for key in criteria},
            "gates": {"permitted": {"status": "pending", "reason": "", "refs": []}}
        } for o in state["options"]}
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, help="папка с state.json, scoring.json и evidence.md")
    parser.add_argument("--rubric", type=Path, default=DEFAULT_RUBRIC)
    parser.add_argument("--init", action="store_true", help="напечатать заготовку scoring.json для вариантов дела")
    args = parser.parse_args()
    try:
        state = read_state(args.case / "state.json")
        rubric = read_json(args.rubric)
        if args.init:
            print(json.dumps(blank_assessment(state, rubric), ensure_ascii=False, indent=2))
            return 0
        case = read_json(args.case / "scoring.json")
        rows = assemble(state, case, rubric, evidence_ids(args.case / "evidence.md"))
        print(make_report(state, case, rubric, rows), end="")
    except (OSError, ValueError) as error:
        print(f"Расчёт прерван — {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
