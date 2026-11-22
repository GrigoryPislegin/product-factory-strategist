"""Собрать или проверить материалы к решению руководителя без вызова модели."""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import deck
import executive
import investment_model
import score
from check import check_presentation, read_state


def assessments(case, state, rubric_path):
    rubric = score.read_json(rubric_path)
    scoring = score.read_json(case / "scoring.json")
    rows = score.assemble(state, scoring, rubric, score.evidence_ids(case / "evidence.md"))
    return scoring, rubric, rows


def scorecard(case, state, rubric_path):
    return score.make_report(state, *assessments(case, state, rubric_path)).encode("utf-8")


def input_record(case, rubric, scoring, decision):
    """Связать выпуск с содержанием источников, включая правки внутри прежнего E-ID."""
    evidence = (case / "evidence.md").read_text(encoding="utf-8")
    sources = {"evidence.md": evidence, "scoring.json": scoring, "rubric": rubric, "decision": decision}
    def digest(value):
        normalized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",",":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    values = {name: digest(value) for name, value in sources.items()}
    return (json.dumps(values, indent=2) + "\n").encode("utf-8")


def safe_name(name, suffix):
    if not isinstance(name, str) or Path(name).name != name or Path(name).suffix.lower() != suffix:
        raise ValueError(f"Нужно имя файла {suffix} из папки дела.")
    return name


def atomic_create(path, data):
    # Полностью записанный файл становится виден целиком. Повтор с тем же результатом безопасен.
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".handoff-", delete=False) as f:
        tmp = Path(f.name)
        try:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        try:
            os.link(tmp, path)
        except FileExistsError:
            if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
                raise ValueError(f"Файл {path.name} уже существует с другим содержанием. Выберите следующую версию.")
    finally:
        tmp.unlink(missing_ok=True)


def prepare(case, state, rubric, version):
    specification = deck.blank_fields(state.get("level", "standard"))
    changes = [o["id"] for o in state["options"] if o["kind"] == "change"]
    if len(changes) >= 2:
        specification["summary_options"] = changes[:2]
    if specification["level"] == "deep":
        name = f"finance-v{version}.csv"
        specification["finance_input"] = name
        if not (case / name).exists():
            atomic_create(case / name, investment_model.blank(changes[:2]))
    templates = {"scoring.json": score.blank_assessment(state, score.read_json(rubric)),
                 f"presentation-v{version}.json": specification}
    for name, payload in templates.items():
        path = case / name
        if path.is_symlink():
            raise ValueError(f"Укажите обычный файл: {name}")
        if not path.exists():
            atomic_create(path, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def handoff(case, version, rubric, verify=False, repair=False):
    if version < 1:
        raise ValueError("Версия должна быть положительной.")
    state = read_state(case / "state.json", verify_presentation=False)
    if state["stage"] == "research":
        raise ValueError("Сначала сформулируйте варианты для обсуждения.")
    scoring, rules, rows = assessments(case, state, rubric)
    report = score.make_report(state, scoring, rules, rows).encode("utf-8")
    brief = executive.render(case, state, scoring, rules, rows, version)
    deck_name = safe_name(state.get("presentation") or f"presentation-v{version}.pptx", ".pptx")
    outputs = [(case / f"scorecard-v{version}.md", report), (case / f"executive-summary-v{version}.html", brief)]
    spec = case / f"presentation-v{version}.json"
    if state.get("level") == "deep" and not spec.is_file():
        raise ValueError(f"Для проверки инвестиционной защиты нужен {spec.name}.")
    if spec.exists():
        inputs = score.read_json(spec)
        rich = "investment" in inputs and state.get("level", inputs.get("level")) == "deep"
        if rich and "finance_input" not in inputs:
            raise ValueError("Для глубокой защиты укажите finance_input с финансовым CSV этой версии.")
        if rich:
            finance = case / safe_name(inputs["finance_input"], ".csv")
            outputs.append((case / f"investment-model-v{version}.xlsx",
                            investment_model.render(finance, inputs.get("summary_options"))))
    if repair and state.get("format_version", 1) == 1 and not spec.exists() and (case / deck_name).exists():
        check_presentation(case, deck_name)
    else:
        spec = case / f"presentation-v{version}.json"
        if not spec.exists():
            raise ValueError(f"Не хватает {spec.name}. Выполните init для этой версии и заполните поля.")
        presentation = score.read_json(spec)
        if "level" in state:
            presentation["level"] = state["level"]
        if presentation.get("summary_options") is not None:
            selected = presentation["summary_options"]
            if not isinstance(selected, list) or len(selected) != 2 or not all(isinstance(x, str) and x in rows for x in selected) or selected[0] == selected[1]:
                raise ValueError("Укажите два разных ID вариантов в summary_options.")
            totals, _ = score.compare(rows, next(iter(rules["profiles"].values())))
            for key, oid in zip(("valueA", "valueB"), selected):
                presentation["slides"][1][key] = f"{score.display_score(totals[oid])} / 100"
        outputs.append((case / deck_name, deck.render(presentation)))
    if state.get("format_version") == 2:
        outputs.append((case / f"basis-v{version}.json", input_record(case, rules, scoring, state.get("decision"))))
    for path, data in outputs:
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.read_bytes() != data)):
            raise ValueError(f"Отличается {path.name}. Сохраните старую версию и укажите новые имена файлов.")
        if verify and not path.exists():
            raise ValueError(f"Не хватает {path.name}. Сначала выполните build.")
    if not verify:
        for path, data in outputs:
            atomic_create(path, data)
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "build", "verify", "repair", "summary"))
    parser.add_argument("case", type=Path)
    parser.add_argument("--version", type=int, help="по умолчанию delivery_version в state.json или 1")
    parser.add_argument("--rubric", type=Path, help="по умолчанию шкала дела или общая шкала проекта")
    args = parser.parse_args()
    try:
        state = read_state(args.case / "state.json", verify_presentation=False)
        rubric = args.rubric or (args.case / safe_name(state["rubric"], ".json") if "rubric" in state else score.DEFAULT_RUBRIC)
        version = args.version if args.version is not None else state.get("delivery_version", 1)
        if type(version) is not int or version < 1:
            raise ValueError("Укажите положительную версию.")
        if args.action == "summary":
            summary = executive.render(args.case, state, *assessments(args.case, state, rubric), version)
            path = args.case / f"executive-summary-v{version}.html"
            atomic_create(path, summary)
            print(path)
        elif args.action == "init":
            prepare(args.case, state, rubric, version)
            print("Входы для скоринга и слайдов готовы к заполнению.")
        else:
            for path, _ in handoff(args.case, version, rubric, args.action == "verify", args.action == "repair"):
                print(path)
            if args.action == "repair":
                print("Перед показом сверьте содержимое сохранённой презентации с текущими выводами.")
    except (OSError, ValueError) as error:
        print(f"Материалы к решению — {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
