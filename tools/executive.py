"""Собрать краткое сравнение для руководителя из проверенных оценок дела."""
from html import escape
from pathlib import Path
from string import Template
from urllib.parse import quote

import score
from check import require_text

TEMPLATE = Path(__file__).resolve().parents[1] / "templates/summary.html"


def render(folder, state, scoring, rubric, rows, version):
    spec_path = folder / f"summary-v{version}.json"
    spec = score.read_json(spec_path) if spec_path.exists() else {}
    if not isinstance(spec, dict) or not isinstance(spec.get("options", {}), dict):
        raise ValueError("Краткое резюме и его варианты должны быть объектами.")
    compact = spec.get("options", {})
    if set(compact) - set(rows):
        raise ValueError("В кратком резюме есть вариант вне карты решения.")
    profile = next(iter(rubric["profiles"]))
    totals, _ = score.compare(rows, rubric["profiles"][profile])
    table = []
    for option in state["options"]:
        oid = option["id"]
        short = compact.get(oid, {})
        if not isinstance(short, dict):
            raise ValueError(f"Проверьте краткое описание {oid}.")
        def field(key, default):
            return escape(require_text(short.get(key, default), f"{oid}.{key}"))
        label = field("label", option["title"])
        gain = field("gain", scoring["assessments"][oid]["strength"])
        risk = field("risk", option["objection"])
        gate = escape(score.ELIGIBILITY[rows[oid]["eligibility"]])
        points = score.display_score(totals[oid])
        table.append(f'<tr><td>{label}</td><td data-label="Польза">{gain}</td>'
                     f'<td data-label="Возражение">{risk}</td><td data-label="Баллы">{points}'
                     f'<span class="gate">{gate}</span></td></tr>')
    decision = state.get("decision")
    def content(key, default):
        return escape(require_text(spec.get(key, default), "summary." + key))
    title = content("title", state["question"])
    lead = content("lead", scoring["next_evidence"])
    ask = content("ask", state["next_step"])
    if decision:
        chosen = next(o for o in state["options"] if o["id"] == decision["option_id"])
        title = escape(chosen["title"])
        lead = escape(decision["quote"])
        ask = escape(state["next_step"])
    metric = '<p class="metric">' + content("metric", "") + '</p>' if "metric" in spec else ""
    card = "scorecard.md" if state.get("format_version", 1) == 1 and (folder / "scorecard.md").is_file() else f"scorecard-v{version}.md"
    files = [(card, "Расчёт по критериям"), ("evidence.md", "Источники"), (state.get("presentation"), "Презентация")]
    links = [f'<a href="./{escape(name, quote=True)}">{label}</a>' for name, label in files
             if isinstance(name, str) and Path(name).name == name]
    attachment = spec.get("strategy_file")
    if attachment:
        file = Path(require_text(attachment, "summary.strategy_file"))
        base = folder.resolve().parent
        target = (folder / file).resolve()
        if file.is_absolute() or base not in target.parents or file.suffix not in (".pdf", ".md"):
            raise ValueError("Укажите локальный документ стратегии рядом с делом.")
        links.insert(0, f'<a href="./{quote(file.as_posix())}">Полная стратегия</a>')
    winners = {score.compare(rows, weights)[1] for weights in rubric["profiles"].values()}
    if len(winners) == 1 and None not in winners:
        leader = next(o["title"] for o in state["options"] if o["id"] in winners)
        conclusion = "Во всех профилях лидирует «" + escape(leader) + "»."
    else:
        conclusion = "При учёте неопределённости и смене весов устойчивого лидера нет."
    note = f'Профиль «{escape(profile)}». Балл — округлённая середина оценок. Подробная карта показывает неопределённость. {conclusion}'
    return Template(TEMPLATE.read_text(encoding="utf-8")).substitute(
        title=title, lead=lead, metric=metric, rows="".join(table), note=note,
        ask_label="Следующий шаг" if decision else "Что решить сейчас", ask=ask, links="".join(links)).encode("utf-8")
