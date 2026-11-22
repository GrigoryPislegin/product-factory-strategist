"""Найти короткие фрагменты в явно перечисленных локальных документах и таблицах."""

import argparse
import csv
import math
import posixpath
import re
import subprocess
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

WORD = re.compile(r"[^\W_]+", re.UNICODE)


def terms(text):
    return set(WORD.findall(text.casefold().replace("ё", "е")))


# Падежные формы сопоставляются только у кириллических слов с достаточно длинной основой.
RUSSIAN = re.compile(r"[а-я]+")
ENDINGS = tuple(sorted(("иями", "ями", "ами", "ого", "его", "ыми", "ими", "ией", "иям", "иях",
                        "ах", "ях", "ам", "ям", "ом", "ем", "ов", "ев", "ую", "юю", "ые", "ие",
                        "ая", "яя", "ой", "ей", "ый", "ий", "ым", "им", "ых", "их", "ое",
                        "ее", "ии", "ия", "ию", "а", "я", "е", "у", "ю", "ы", "и", "ь"),
                       key=len, reverse=True))
STOP_WORDS = {"и", "в", "во", "на", "с", "со", "по", "от", "к", "ко", "из", "для", "а", "о", "об"}
SOURCE_ERRORS = (OSError, ValueError, BadZipFile, ET.ParseError, KeyError, IndexError, subprocess.SubprocessError, csv.Error)


@lru_cache(maxsize=8192)
def word_form(word):
    if RUSSIAN.fullmatch(word):
        for ending in ENDINGS:
            if word.endswith(ending) and len(word) - len(ending) >= 4:
                return word[:-len(ending)]
    return word


def excerpt(text, matched, budget=900):
    text = " ".join(text.split())
    if len(text) <= budget:
        return text
    pos = next((m.start() for m in WORD.finditer(text)
                if m.group().casefold().replace("ё", "е") in matched), 0)
    start = max(0, min(pos - budget // 4, len(text) - budget))
    return ("…" if start else "") + text[start:start + budget] + ("…" if start + budget < len(text) else "")


def spreadsheet(path):
    with ZipFile(path) as z:
        book = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        locations = {r.get("Id"): r.get("Target") for r in rels if r.get("TargetMode") != "External"}
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in item.findall(".//{*}t")) for item in ss]
        for tab in book.findall("{*}sheets/{*}sheet"):
            rid = next((v for k, v in tab.attrib.items() if k.endswith("}id")), None)
            target = locations.get(rid)
            if not target:
                continue
            member = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
            if not member.startswith("xl/worksheets/"):
                continue
            with z.open(member) as stream:
                header = {}
                for _, row in ET.iterparse(stream, events=("end",)):
                    if row.tag.split("}")[-1] != "row":
                        continue
                    cells = []
                    for cell in row.findall("{*}c"):
                        address = cell.get("r", "")
                        value = cell.findtext("{*}v", "")
                        if cell.get("t") == "s" and value:
                            value = shared[int(value)]
                        if cell.get("t") == "inlineStr":
                            value = "".join(t.text or "" for t in cell.findall(".//{*}t"))
                        formula = cell.find("{*}f")
                        if formula is not None:
                            value = f"={formula.text or '[общая формула]'} (кэш: {value or 'нет'})"
                        if value:
                            cells.append((address, value))
                    if cells:
                        annotated = []
                        for addr, value in cells:
                            col = addr.rstrip("0123456789")
                            label = header.get(col, "")
                            annotated.append(f"{addr} {label} {value}".strip())
                        yield f"{tab.get('name')}!{cells[0][0]}:{cells[-1][0]}", " | ".join(annotated)
                        if not header:
                            header = {a.rstrip("0123456789"): v for a, v in cells}
                    row.clear()


def paragraphs(text):
    for block in re.split(r"\n\s*\n", text):
        block = " ".join(block.split())
        # Границы окна относятся к тому же физическому локатору.
        for start in range(0, len(block), 650):
            yield block[max(0, start - 60):start + 650]


def fragments(path):
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt"):
        for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            for part in paragraphs(line):
                yield f"строка {n}", part
    elif suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader, [])
            for n, row in enumerate(reader, 2):
                yield f"запись {n}", " | ".join(f"{header[i] if i < len(header) else i + 1}={v}" for i, v in enumerate(row))
    elif suffix == ".docx":
        with ZipFile(path) as z:
            doc = ET.fromstring(z.read("word/document.xml"))
            for n, p in enumerate(doc.findall(".//{*}p"), 1):
                for part in paragraphs("".join(t.text or "" for t in p.findall(".//{*}t"))):
                    yield f"абзац {n}", part
    elif suffix == ".xlsx":
        yield from spreadsheet(path)
    elif suffix == ".pdf":
        result = subprocess.run(["pdftotext", "-layout", str(path.resolve()), "-"], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True, timeout=90)
        for page, content in enumerate(result.stdout.decode("utf-8").split("\f"), 1):
            for part in paragraphs(content):
                yield f"стр. {page}", part
    else:
        raise ValueError(f"Формат {suffix} не поддержан. Для сайта откройте первичную страницу инструментом клиента.")


def search(paths, query, limit, *, exact=False, errors=None):
    wanted = terms(query)
    if not wanted or limit < 1:
        raise ValueError("Укажите слова запроса и положительный лимит.")
    if not exact:
        wanted = wanted - STOP_WORDS or wanted
    normalize = (lambda word: word) if exact else word_form
    query_forms = {normalize(word) for word in wanted}
    docs, counts = [], Counter()
    total = 0
    for path in paths:
        try:
            for locator, content in fragments(path):
                total += 1
                matched = {word for word in terms(content) if normalize(word) in query_forms}
                if matched:
                    covered = {normalize(word) for word in matched}
                    counts.update(covered)
                    docs.append((path, locator, content, matched, covered))
        except SOURCE_ERRORS as error:
            if errors is None:
                raise
            errors.append((path, str(error)))
    def rank(doc):
        literal_hits = len(wanted & doc[3])
        rarity = sum(math.log((total + 1) / (counts[t] + 1)) for t in sorted(doc[4]))
        return len(doc[4]), literal_hits, rarity
    return [doc[:4] for doc in sorted(docs, key=rank, reverse=True)[:limit]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--exact", action="store_true", help="только буквальные совпадения слов")
    args = parser.parse_args()
    try:
        errors = []
        matches = search(args.files, args.query, args.limit, exact=args.exact, errors=errors)
        for path, locator, content, matched in matches:
            print(f"{path} · {locator} · совпало: {', '.join(sorted(matched))}\n{excerpt(content, matched)}\n")
        if not matches:
            print("Совпадений нет. Уточните формулировку или откройте источник по разделам.")
        for path, error in errors:
            print(f"Источник проверен не полностью — {path}: {error}", file=sys.stderr)
        if errors:
            return 2
    except SOURCE_ERRORS as err:
        print(f"Поиск прерван — {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
