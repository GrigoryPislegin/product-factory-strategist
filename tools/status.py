"""Короткий снимок дела и ближайшее действие для новой сессии."""

import argparse
import contextlib
import io
from pathlib import Path
import sys

from check import check_presentation, check_state, read_state


def clip(text, limit=270):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def snapshot(folder):
    file = folder / "state.json"
    state = read_state(file, verify_presentation=False)
    stage = state["stage"]
    lines = [f"Этап: {stage}", f"Вопрос: {clip(state['question'])}", f"Следующий шаг: {clip(state['next_step'])}"]
    decision = state.get("decision")
    lines.append("Выбор: открыт" if not decision else f"Выбор: {decision['option_id']} — {clip(decision['quote'])}")
    for o in state["options"][:8]:
        lines.append(f"- {o['id']} · {clip(o['title'], 105)}. Возражение: {clip(o['objection'], 150)}")
    if len(state["options"]) > 8:
        lines.append(f"Другие варианты: {len(state['options']) - 8}. Полный список в state.json.")
    if state.get("format_version") == 2 and stage in ("awaiting_choice", "complete"):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                check_state(file)
            lines.append("Карта, основания и презентация совпадают с сохранённой версией.")
        except (OSError, ValueError) as error:
            lines.append(f"Проверка выдачи: {clip(str(error))}")
            if not (folder / "scoring.json").is_file():
                lines.append("Выполните tools/handoff.py init для дела и заполните scoring.json.")
            lines.append("Пропущенные файлы восстановите через tools/handoff.py repair. При расхождении сохраните прежнюю выдачу и соберите новую версию.")
    elif stage == "complete" and state.get("presentation"):
        try:
            check_presentation(folder, state["presentation"])
        except (OSError, ValueError) as error:
            lines.append(f"Проверка презентации: {clip(str(error))}")
    summary_name = f"executive-summary-v{state.get('delivery_version', 1)}.html"
    if (folder / summary_name).is_file():
        lines.append(f"Краткое сравнение: {summary_name}")
    for field in ("output", "presentation"):
        name = state.get(field)
        if isinstance(name, str) and Path(name).name == name and (folder / name).is_file():
            lines.append(f"{field}: {name}")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("case", type=Path)
    args = p.parse_args()
    try:
        print(snapshot(args.case))
    except (ValueError, OSError) as error:
        print(f"Снимок недоступен — {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
