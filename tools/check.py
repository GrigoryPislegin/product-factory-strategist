"""Read-only checks for a strategy case and for the baseline CSV."""

import argparse
import csv
import json
import sys
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile
from decimal import Decimal, InvalidOperation
from pathlib import Path


def require_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Заполните поле {field}.")
    return value.strip()


def require_alternatives(options):
    if len(options) < 3 or not {"status_quo", "close", "change"}.issubset(o["kind"] for o in options):
        raise ValueError("Нужны разные пути, в том числе status_quo, close и change.")


def presentation_path(folder, name):
    name = require_text(name, "presentation")
    path = folder / name
    if Path(name).name != name or path.suffix.lower() != ".pptx" or path.is_symlink():
        raise ValueError("Укажите PPTX из папки дела.")
    return path


def check_presentation(folder, name):
    path = presentation_path(folder, name)
    try:
        with ZipFile(path) as deck:
            root = ElementTree.fromstring(deck.read("ppt/presentation.xml"))
            if not root.findall("{*}sldIdLst/{*}sldId") or not any(
                    entry.startswith("ppt/slides/slide") and entry.endswith(".xml") for entry in deck.namelist()):
                raise ValueError("В презентации отсутствуют слайды.")
    except (BadZipFile, KeyError, ElementTree.ParseError) as error:
        raise ValueError("Указан некорректный файл презентации.") from error


def read_state(path, *, verify_presentation=True):
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("Состояние должно быть объектом JSON.")
    if state.get("level", "standard") not in ("quick", "standard", "deep"):
        raise ValueError("Укажите уровень quick, standard или deep.")
    stage = state.get("stage")
    if stage not in ("research", "awaiting_choice", "strategy", "complete"):
        raise ValueError("Неизвестный этап.")
    require_text(state.get("question"), "question")
    require_text(state.get("next_step"), "next_step")
    options = state.get("options")
    if not isinstance(options, list):
        raise ValueError("options должно содержать список вариантов.")
    ids = set()
    for option in options:
        if not isinstance(option, dict):
            raise ValueError("Каждый вариант задаётся отдельным объектом.")
        option_id = require_text(option.get("id"), "options.id")
        if option_id in ids:
            raise ValueError(f"Повторяется ID варианта {option_id}.")
        ids.add(option_id)
        kind = require_text(option.get("kind"), "options.kind")
        if kind not in ("status_quo", "close", "change"):
            raise ValueError(f"Неизвестный тип варианта {kind}.")
        require_text(option.get("title"), "options.title")
        require_text(option.get("objection"), "options.objection")
    if stage != "research":
        require_alternatives(options)
    decision = state.get("decision")
    if stage in ("strategy", "complete"):
        if not isinstance(decision, dict):
            raise ValueError("Сначала зафиксируйте выбор руководителя.")
        selected = require_text(decision.get("option_id"), "decision.option_id")
        if selected not in ids:
            raise ValueError("Выбранный вариант отсутствует в текущем сравнении.")
        require_text(decision.get("quote"), "decision.quote")
    elif decision is not None:
        raise ValueError("На открытом этапе поле decision должно быть null.")
    if stage == "complete":
        name = require_text(state.get("output"), "output")
        report = path.parent / name
        if (Path(name).name != name or name in (".", "..")
                or report.suffix.lower() != ".md" or report.is_symlink()
                or not report.is_file() or not report.read_text(encoding="utf-8").strip()):
            raise ValueError("Укажите непустой Markdown-документ результата в папке состояния.")
    version = state.get("format_version", 1)
    if type(version) is not int or version not in (1, 2):
        raise ValueError("Неизвестная версия формата дела.")
    if stage == "complete" and (version == 2 or "presentation" in state):
        if verify_presentation:
            check_presentation(path.parent, state.get("presentation"))
        else:
            presentation_path(path.parent, state.get("presentation"))
    return state


def check_state(path):
    state = read_state(path)
    if state.get("format_version") == 2 and state["stage"] in ("awaiting_choice", "complete"):
        from handoff import handoff, safe_name
        from score import DEFAULT_RUBRIC
        version = state.get("delivery_version", 1)
        if type(version) is not int or version < 1:
            raise ValueError("Укажите положительное целое delivery_version.")
        rubric = path.parent / safe_name(state["rubric"], ".json") if "rubric" in state else DEFAULT_RUBRIC
        handoff(path.parent, version, rubric, verify=True)
    print(f"{state['stage']} — {state['question'].strip()}\nСледующий шаг — {state['next_step'].strip()}")


def show_gaps(path):
    columns = {"metric", "unit", "next_year_status_quo", "next_year_min_target"}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = columns.difference(reader.fieldnames or [])
        if missing:
            raise ValueError("В CSV отсутствуют колонки " + ", ".join(sorted(missing)))
        results = []
        for row in reader:
            metric = require_text(row["metric"], "metric")
            unit = require_text(row["unit"], "unit")
            base = Decimal(require_text(row["next_year_status_quo"], "next_year_status_quo"))
            target = Decimal(require_text(row["next_year_min_target"], "next_year_min_target"))
            if not base.is_finite() or not target.is_finite():
                raise ValueError(f"Для {metric} нужны конечные числа.")
            gap_unit = "п.п." if unit == "%" else unit
            results.append(f"{metric} ({gap_unit}) — {target - base}")
        if not results:
            raise ValueError("В CSV отсутствуют строки показателей.")
        print("\n".join(results))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("state", "gaps"))
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "state":
            check_state(args.file)
        else:
            show_gaps(args.file)
    except (OSError, ValueError, InvalidOperation, csv.Error) as error:
        print(f"Проверка прервана — {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
