"""Собрать редактируемую презентацию из JSON и комплектного шаблона PowerPoint."""

import argparse
import io
import depth
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import BadZipFile, ZipFile

TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "strategy-deck.pptx"
PART = re.compile(r"ppt/(?:slides/slide|notesSlides/notesSlide)([1-9]\d*)\.xml")
FIELD = re.compile(r"\{\{([a-zA-Z]+)\}\}")


def render(spec, template=None):
    slides = spec.get("slides") if isinstance(spec, dict) else None
    if not isinstance(slides, list) or not slides or not isinstance(slides[0], dict):
        raise ValueError("Поле slides должно содержать список экранов.")
    if spec.get("level") == "deep" and isinstance(spec.get("investment"), dict):
        overrides = spec["investment"].get("core_text", {})
        if not isinstance(overrides, dict):
            raise ValueError("core_text должен содержать поля основных слайдов.")
        slides = list(slides)
        for number, fields in overrides.items():
            if number not in {str(i) for i in range(1,len(slides)+1)} or not isinstance(fields,dict):
                raise ValueError("Укажите корректный слайд и поля в core_text.")
            if number == "2" and {"valueA","valueB"} & fields.keys():
                raise ValueError("Баллы executive summary определяются картой решений.")
            idx = int(number)-1
            if not isinstance(slides[idx],dict) or not fields.keys() <= slides[idx].keys():
                raise ValueError("Неизвестное поле основного слайда в core_text.")
            slides[idx] = {**slides[idx], **fields}
        if len(slides)>1 and isinstance(slides[1],dict):
            summary = dict(slides[1])
            for field in ("valueA","valueB"):
                value = summary.get(field)
                if isinstance(value,str) and re.fullmatch(r"\d{1,3}\s*/\s*100",value.strip()):
                    summary[field] = "Скоринг " + value.strip()
            slides[1] = summary
    if template is None:
        template = TEMPLATE if spec.get("layout") == "strategy-v2" or "summary" in slides[0] else TEMPLATE.with_name("strategy-deck-v1.pptx")
    with ZipFile(template) as master:
        slide_count = sum(bool(re.fullmatch(r"ppt/slides/slide\d+\.xml", name)) for name in master.namelist())
        if len(slides) != slide_count:
            raise ValueError(f"Шаблон содержит {slide_count} слайдов.")
        seen = [set() for _ in slides]
        output = io.BytesIO()
        with ZipFile(output, "w") as deck:
            for item in master.infolist():
                raw = master.read(item)
                match = PART.fullmatch(item.filename)
                if match:
                    index = int(match[1]) - 1
                    slide = slides[index]
                    if not isinstance(slide, dict):
                        raise ValueError(f"Слайд {index + 1} должен быть объектом.")

                    def replace(field):
                        key = field[1]
                        text = slide.get(key)
                        if not isinstance(text, str) or not text.strip():
                            raise ValueError(f"Слайд {index + 1} — заполните {key}.")
                        if any((ord(c) < 32 and c not in "\t\r\n")
                               or 0xD800 <= ord(c) <= 0xDFFF or ord(c) in (0xFFFE, 0xFFFF) for c in text):
                            raise ValueError(f"Слайд {index + 1}, {key} — недопустимый управляющий символ.")
                        seen[index].add(key)
                        return escape(" ".join(text.split()))

                    raw = FIELD.sub(replace, raw.decode("utf-8")).encode("utf-8")
                deck.writestr(item, raw)
        for n, (slide, keys) in enumerate(zip(slides, seen), 1):
            extra = set(slide) - keys
            if not keys or extra:
                raise ValueError(f"Проверьте поля слайда {n}: {', '.join(sorted(extra))}")
    return depth.apply(output.getvalue(), spec) if spec.get("layout") == "strategy-v2" else output.getvalue()


def blank_fields(level=None):
    with ZipFile(TEMPLATE) as master:
        fields = {}
        for name in master.namelist():
            part = PART.fullmatch(name)
            if part:
                slide = fields.setdefault(int(part[1]), {})
                slide.update(dict.fromkeys(FIELD.findall(master.read(name).decode("utf-8")), ""))
    spec = {"layout": "strategy-v2", "slides": [fields[n] for n in sorted(fields)]}
    if level:
        spec["level"] = level
    if level == "deep":
        spec["finance_input"] = "finance-v1.csv"
        spec["investment"] = json.loads((TEMPLATE.parent / "investment-plan.json").read_text(encoding="utf-8"))
    return spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", choices=("quick","standard","deep"), help="глубина результата")
    parser.add_argument("--init", action="store_true", help="напечатать пустые поля шаблона для нового дела")
    parser.add_argument("spec", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args()
    try:
        if args.init:
            if args.spec or args.output:
                parser.error("--init выводит JSON в stdout и не принимает путь.")
            print(json.dumps(blank_fields(args.level), ensure_ascii=False, indent=2))
            return 0
        if not args.spec or not args.output:
            parser.error("Для сборки укажите входной JSON и выходной PPTX.")
        if args.output.suffix.lower() != ".pptx":
            raise ValueError("Выходной файл должен иметь расширение .pptx.")
        specification = json.loads(args.spec.read_text(encoding="utf-8"))
        if args.level:
            specification["level"] = args.level
        data = render(specification)
        with args.output.open("xb") as stream:
            stream.write(data)
    except (OSError, ValueError, BadZipFile) as error:
        print(f"Презентация не сохранена — {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
