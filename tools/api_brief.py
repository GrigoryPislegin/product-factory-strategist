"""Компактная редактируемая презентация из завершённого API-дела."""
import io
import re
import textwrap
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from consulting import ConsultingSlide
from deck import TEMPLATE
from investment import A, P, BLUE, INK, LINE, NAVY, PALE, BAD_XML, sub


def clean(value):
    # Control characters can occur in plain text but cannot be embedded in OOXML.
    return BAD_XML.sub(" ", value)


def block(slide, x, y, width, height, value, size, color=INK, bold=False):
    """Bound the displayed excerpt; full source text is retained in speaker notes."""
    width_chars = max(8, int(width / (size * .62)))
    max_lines = max(1, int(height / (size * 1.20)))
    lines = textwrap.wrap(" ".join(clean(value).split()), width_chars,
                          max_lines=max_lines, placeholder="…", break_on_hyphens=False)
    if lines:
        slide.label(x, y, width, height, "\n".join(lines), size, bold, color)


def section(slide, y, caption, value, height):
    slide.component("card", 45, y-9, 1188, height+55)
    slide.pill(60,y, max(160, len(caption)*10+30), caption)
    block(slide, 60, y + 42, 1160, height, value, 27)


def full_notes(root, paragraphs):
    for shape in root.findall(".//{*}sp"):
        ph = shape.find(".//{*}ph")
        if ph is not None and ph.get("type") == "body":
            body = shape.find(f"{{{P}}}txBody")
            for p in list(body.findall(f"{{{A}}}p")):
                body.remove(p)
            for value in paragraphs:
                for line in clean(value).splitlines() or [""]:
                    p = sub(body, A, "p")
                    sub(sub(p, A, "r"), A, "t").text = line
            return
    raise ValueError("В шаблоне отсутствует поле заметок.")


def page(slide, number, state):
    research, decision, strategy = state["research"], state["decision"], state["strategy"]
    title = ("Решение руководителя", "Сравнение вариантов", "Основания решения",
             "Продуктовая стратегия", "Коммуникационная стратегия", "Проверка и следующий шаг")[number - 1]
    slide.root.set("showMasterSp", "0")
    slide.navigation("Стратегия продукта", ["Решение","Основания","Стратегия","Проверка"], (0,0,1,2,2,3)[number-1], number)
    slide.label(55, 69, 1170, 64, title, 38, True, NAVY)
    slide.shape(60, 135, 1160, 2, LINE)
    if number == 1:
        section(slide, 169, "Вопрос", state["question"], 96)
        section(slide, 326, "Выбранный вариант", decision["title"], 95)
        section(slide, 484, "Основание руководителя", decision["reason"], 155)
        return [state["question"], decision["title"], decision["reason"]]
    if number == 2:
        columns = [(58, 302, "Вариант"), (382, 395, "Польза"), (800, 420, "Возражение")]
        slide.shape(52, 159, 1176, 50, PALE)
        for x, w, heading in columns:
            slide.label(x + 8, 171, w - 10, 31, heading, 21, True, NAVY)
        options = research["options"]
        height = min(136, 466 // len(options))
        notes = []
        for index, option in enumerate(options):
            y = 213 + index * height
            for (x, w, heading), key in zip(columns, ("title", "benefit", "objection")):
                block(slide, x + 8, y + 9, w - 10, height - 15, option[key], 20,
                      NAVY if key == "title" else INK, key == "title")
                notes.append(f"{heading}: {option[key]}")
            slide.shape(58, y + height - 1, 1162, 1, LINE)
        return notes
    if number == 3:
        notes = []
        for x in (44,648):slide.component("card",x,158,584,510)
        for x, caption, entries, empty in (
            (60, "Подтверждения", research["evidence"], "В деле нет цитат из файлов."),
            (665, "Что ещё проверить", research["gaps"], "В сравнении не указаны пробелы."),
        ):
            slide.pill(x, 174, 226, caption)
            notes.extend([caption, *(entries or [empty])])
            shown = entries[:3] or [empty]
            for index, entry in enumerate(shown):
                block(slide, x, 233 + index * 143, 545, 126, entry, 21)
        return notes
    if number in (4, 5):
        value = strategy["product" if number == 4 else "communication"]
        # Use paragraph/sentence boundaries already present in the saved strategy.
        paragraphs = [p.strip() for p in re.split(r"\n+|(?<=[.!?])\s+(?=[А-ЯЁA-Z])", value) if p.strip()]
        shown = paragraphs[:4]
        height = min(170, 480 // max(1, len(shown)))
        for index, paragraph in enumerate(shown):
            y = 178 + index * height
            slide.component("card", 44, y-9, 1190, height-6)
            block(slide, 68, y+4, 1130, height-27, paragraph, 27)
        return [value]
    section(slide, 166, "Как измеряем результат", strategy["measurement"], 195)
    section(slide, 424, "Кто делает следующий шаг", strategy["next_step"], 202)
    return [strategy["measurement"], strategy["next_step"]]


def render(state):
    """Keep the template's native six-slide layout, masters, links and theme."""
    output = io.BytesIO()
    with ZipFile(TEMPLATE) as source, ZipFile(output, "w") as dest:
        changed = {}
        for n in range(1, 7):
            name = f"ppt/slides/slide{n}.xml"
            slide = ConsultingSlide(ET.fromstring(source.read(name)))
            paragraphs = page(slide, n, state)
            changed[name] = ET.tostring(slide.root, encoding="utf-8", xml_declaration=True)
            name = f"ppt/notesSlides/notesSlide{n}.xml"
            notes = ET.fromstring(source.read(name))
            full_notes(notes, paragraphs)
            changed[name] = ET.tostring(notes, encoding="utf-8", xml_declaration=True)
        for file in source.infolist():
            dest.writestr(file, changed[file.filename] if file.filename in changed else source.read(file))
    return output.getvalue()
