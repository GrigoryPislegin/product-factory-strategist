import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import score


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo" / "family" / "first-run"
RUBRIC = score.read_json(score.DEFAULT_RUBRIC)
STATE = score.read_state(DEMO / "state.json")
CASE = score.read_json(DEMO / "scoring.json")
IDS = score.evidence_ids(DEMO / "evidence.md")


class StrategyScoreTests(unittest.TestCase):
    def test_demo_source_matches_every_option_and_leaves_choice_open(self):
        before = (DEMO / "state.json").read_bytes()
        rows = score.assemble(STATE, CASE, RUBRIC, IDS)
        totals, winner = score.compare(rows, RUBRIC["profiles"]["Равные веса"])
        self.assertIsNone(winner)
        self.assertEqual(set(totals), {o["id"] for o in STATE["options"]})
        self.assertEqual(totals["own_reminder"], totals["family_signal"])
        self.assertEqual(score.span(totals["family_signal"], 4), "12,5–93,75")
        report = subprocess.check_output([sys.executable, str(ROOT / "tools/score.py"), str(DEMO)])
        self.assertEqual(report, (DEMO / "scorecard.md").read_bytes())
        self.assertEqual((DEMO / "state.json").read_bytes(), before)
        self.assertIsNone(STATE["decision"])

    def test_missing_evidence_keeps_entire_range_and_zero_is_known(self):
        def record(band, basis, refs):
            return {"band": band, "basis": basis, "reason": "проверка", "refs": refs}

        self.assertEqual(score.bounds(record(None, "unknown", []), IDS, "test"), (0, 4))
        self.assertEqual(score.bounds(record([0, 0], "evidence", ["E1"]), IDS, "test"), (0, 0))
        for invalid in (record([4, 4], "assumption", []), record([4, 4], "evidence", ["E999"]),
                        record([0, 0], "unknown", ["E1"]), record([3, 2], "evidence", ["E1"]),
                        record([False, 4], "evidence", ["E1"]), record([-1, 5], "evidence", ["E1"])):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                score.bounds(invalid, IDS, "test")

    def test_changing_evidence_changes_only_affected_scores(self):
        original = score.assemble(STATE, CASE, RUBRIC, IDS)
        with_data = copy.deepcopy(CASE)
        with_data["assessments"]["family_signal"]["criteria"]["client"] = {
            "band": [3, 3], "basis": "evidence", "reason": "Синтетический результат пилота.", "refs": ["E10"]}
        changed = score.assemble(STATE, with_data, RUBRIC, IDS | {"E10"})
        weights = RUBRIC["profiles"]["Равные веса"]
        before, _ = score.compare(original, weights)
        after, winner = score.compare(changed, weights)
        self.assertEqual(after.pop("family_signal"), (125, 350))
        before.pop("family_signal")
        self.assertEqual(before, after)
        self.assertIsNone(winner)

    def test_weights_change_winner_and_ties_remain_open(self):
        rows = {"one": {"bands": {"money": (4, 4), "time": (0, 0)}, "eligibility": "clear"},
                "two": {"bands": {"money": (0, 0), "time": (4, 4)}, "eligibility": "clear"}}
        self.assertEqual(score.compare(rows, {"money": 60, "time": 40})[1], "one")
        self.assertEqual(score.compare(rows, {"money": 40, "time": 60})[1], "two")
        self.assertIsNone(score.compare(rows, {"money": 50, "time": 50})[1])
        totals, _ = score.compare(rows, {"money": 100, "time": 0})
        self.assertEqual(totals, {"one": (400, 400), "two": (0, 0)})

    def test_open_gate_competes_but_cannot_win_failed_gate_excludes(self):
        rows = {"high": {"bands": {"x": (4, 4)}, "eligibility": "pending"},
                "other": {"bands": {"x": (2, 2)}, "eligibility": "clear"}}
        self.assertIsNone(score.compare(rows, {"x": 100})[1])
        rows["high"]["eligibility"] = "blocked"
        self.assertEqual(score.compare(rows, {"x": 100})[1], "other")
        rows["other"]["eligibility"] = "blocked"
        self.assertIsNone(score.compare(rows, {"x": 100})[1])

    def test_unverified_competitor_with_overlapping_range_prevents_unique_lead(self):
        rows = {"lead": {"bands": {"x": (3, 4)}, "eligibility": "clear"},
                "open": {"bands": {"x": (1, 3)}, "eligibility": "pending"}}
        self.assertIsNone(score.compare(rows, {"x": 100})[1])
        rows["open"]["bands"]["x"] = (1, 2)
        self.assertEqual(score.compare(rows, {"x": 100})[1], "lead")

    def test_missing_option_criterion_or_constraint_requires_a_new_assessment(self):
        for parent, key in (((), "close"), (("close", "gates"), "authority"),
                            (("own_reminder", "criteria"), "economics")):
            candidate = copy.deepcopy(CASE)
            node = candidate["assessments"]
            for part in parent:
                node = node[part]
            del node[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                score.assemble(STATE, candidate, RUBRIC, IDS)

    def test_early_research_cannot_declare_a_winner_without_alternatives(self):
        state = dict(STATE, stage="research", options=STATE["options"][:2])
        with self.assertRaisesRegex(ValueError, "status_quo"):
            score.assemble(state, CASE, RUBRIC, IDS)

    def test_invalid_weights_and_unsourced_gate_are_rejected(self):
        for value in (24, True, -10):
            rubric = copy.deepcopy(RUBRIC)
            rubric["profiles"]["Равные веса"]["client"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                score.validate_rubric(rubric)
        case = copy.deepcopy(CASE)
        item = case["assessments"]["family_signal"]["gates"]["authority"]
        for status in ("na", "pass", "fail"):
            item.update(status=status, refs=[])
            with self.subTest(status=status), self.assertRaises(ValueError):
                score.assemble(STATE, case, RUBRIC, IDS)
        item["refs"] = ["E2"]
        self.assertEqual(score.assemble(STATE, case, RUBRIC, IDS)["family_signal"]["eligibility"], "blocked")

    def test_both_evidence_formats_reject_duplicates_and_mentions(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Path(folder) / "evidence.md"
            ledger.write_text("| E1 | Ссылается на E5 |\n- **E2, факт.** Обсуждается E9.\n", encoding="utf-8")
            self.assertEqual(score.evidence_ids(ledger), {"E1", "E2"})
            with ledger.open("a", encoding="utf-8") as stream:
                stream.write("- **E1** Повтор.\n")
            with self.assertRaises(ValueError):
                score.evidence_ids(ledger)
            ledger.write_text('{"first":1,"first":2}', encoding="utf-8")
            with self.assertRaises(ValueError):
                score.read_json(ledger)

    def test_new_case_scaffold_reads_only_state_and_is_not_a_completed_evaluation(self):
        with tempfile.TemporaryDirectory() as folder:
            state_file = Path(folder) / "state.json"
            state_file.write_bytes((DEMO / "state.json").read_bytes())
            result = subprocess.check_output([sys.executable, str(ROOT / "tools/score.py"), folder, "--init"])
            template = json.loads(result)
            self.assertEqual(set(template["assessments"]), set(CASE["assessments"]))
            self.assertEqual([p.name for p in Path(folder).iterdir()], ["state.json"])
            with self.assertRaises(ValueError):
                score.assemble(STATE, template, RUBRIC, set())


if __name__ == "__main__":
    unittest.main()
