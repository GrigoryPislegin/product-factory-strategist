import io
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import find_evidence
import usage


class ResearchToolsTests(unittest.TestCase):
    def test_workbook_returns_cell_formula_cached_value_and_shared_text(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.xlsx"
            with ZipFile(path, "w") as z:
                z.writestr("xl/workbook.xml", '<w xmlns:r="r"><sheets><sheet name="Рынок" r:id="a"/></sheets></w>')
                z.writestr("xl/_rels/workbook.xml.rels", '<r><rel Id="a" Target="/xl/worksheets/sheet2.xml"/></r>')
                z.writestr("xl/sharedStrings.xml", '<ss><si><t>Вклад</t></si></ss>')
                z.writestr("xl/worksheets/sheet2.xml", '<ws><row><c r="B1" t="s"><v>0</v></c></row>'
                           '<row><c r="B2"><f>3*5</f><v>15</v></c></row></ws>')
            result = find_evidence.search([path], "вклад 15", 1)
            self.assertEqual(result[0][1], "Рынок!B2:B2")
            self.assertIn("=3*5 (кэш: 15)", result[0][2])

    def test_csv_multiline_record_and_text_casefold(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "источник.csv"
            path.write_text('место,результат\n"А\nБ",Платёж\n', encoding="utf-8-sig")
            hit = find_evidence.search([path], "платеж", 1)
            self.assertEqual(hit[0][1], "запись 2")
            self.assertIn("результат=Платёж", hit[0][2])
            self.assertEqual(find_evidence.search([path], "интервью", 1), [])

    def test_usage_excludes_cache_from_uncached_and_never_counts_reasoning_twice(self):
        events = [
            {"type":"item.completed", "item":{"usage":{"input_tokens":1000}}},
            {"type":"turn.completed", "usage":{"input_tokens":100, "cached_input_tokens":40,
                                               "output_tokens":10, "reasoning_output_tokens":3}},
            {"type":"turn.completed", "usage":{"input_tokens":20, "cached_input_tokens":10, "output_tokens":5}}]
        result = usage.parse_codex(io.StringIO("\n".join(map(json.dumps, events))))
        self.assertEqual(result["total_tokens"], 135)
        self.assertEqual(result["cached_input_tokens"], 50)
        self.assertEqual(usage.estimate(result, list(map(Decimal, ("1", "0.5", "5")))), Decimal("0.00017"))

    def test_missing_cache_is_unknown_and_incomplete_trace_is_not_a_free_run(self):
        text = '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":2}}'
        result = usage.parse_codex(io.StringIO(text))
        self.assertIsNone(result["cached_input_tokens"])
        with self.assertRaises(ValueError):
            usage.estimate(result, [Decimal(1)] * 3)
        for invalid in ("{}", '{"type":"turn.completed","usage":{"input_tokens":2,"cached_input_tokens":3,"output_tokens":0}}'):
            with self.assertRaises(ValueError):
                usage.parse_codex(io.StringIO(invalid))

    def test_russian_forms_keep_literal_priority_and_concrete_source_word(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.md"
            path.write_text("Проверка продуктовой стратегии.\nПродуктовая стратегия.\nТариф 111 и два номера.")
            hits = find_evidence.search([path], "Продуктовая стратегия", 3)
            self.assertEqual([h[1] for h in hits], ["строка 2", "строка 1"])
            self.assertEqual(hits[1][3], {"продуктовой", "стратегии"})
            self.assertEqual(len(find_evidence.search([path], "продуктовая стратегия", 5, exact=True)), 1)
            self.assertFalse(find_evidence.search([path], "номерок 11", 4))

    def test_unavailable_source_keeps_valid_hits_and_reports_partial_coverage(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.md"
            path.write_text("Вклад оплаченного месяца.")
            missing = path.with_name("пропуск.xlsx")
            errors = []
            hits = find_evidence.search([missing, path], "месяц", 1, errors=errors)
            self.assertEqual(hits[0][1], "строка 1")
            self.assertEqual(errors[0][0], missing)
