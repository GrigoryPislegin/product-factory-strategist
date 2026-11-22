import json
import shutil
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO

import check
import handoff
import score

DEMO = Path(__file__).resolve().parents[1] / "demo/family/first-run"


class HandoffTests(unittest.TestCase):
    def test_missing_score_blocks_choice_and_recovery_preserves_human_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp)
            state = json.loads((DEMO / "state.json").read_text())
            state.update(format_version=2, delivery_version=1, presentation="presentation-v1.pptx")
            path = case / "state.json"
            path.write_text(json.dumps(state))
            before = path.read_bytes()
            shutil.copy(DEMO / "evidence.md", case / "evidence.md")
            with self.assertRaises(FileNotFoundError):
                check.check_state(path)
            handoff.prepare(case, state, score.DEFAULT_RUBRIC, 1)
            with self.assertRaises(ValueError):
                handoff.handoff(case, 1, score.DEFAULT_RUBRIC)
            self.assertFalse((case / "scorecard-v1.md").exists())
            shutil.copy(DEMO / "scoring.json", case / "scoring.json")
            shutil.copy(DEMO / "presentation.json", case / "presentation-v1.json")
            handoff.handoff(case, 1, score.DEFAULT_RUBRIC)
            handoff.handoff(case, 1, score.DEFAULT_RUBRIC, verify=True)
            handoff.handoff(case, 1, score.DEFAULT_RUBRIC)
            with redirect_stdout(StringIO()):
                check.check_state(path)
            self.assertEqual(path.read_bytes(), before)
            old = (case / "presentation-v1.pptx").read_bytes()
            (case / "scorecard-v1.md").unlink()
            handoff.handoff(case, 1, score.DEFAULT_RUBRIC, repair=True)
            self.assertEqual((case / "presentation-v1.pptx").read_bytes(), old)
            self.assertTrue((case / "scorecard-v1.md").is_file())
            spec = json.loads((case / "presentation-v1.json").read_text())
            spec["slides"][0]["title"] = "Новые основания"
            (case / "presentation-v1.json").write_text(json.dumps(spec))
            with self.assertRaisesRegex(ValueError, "Отличается"):
                handoff.handoff(case, 1, score.DEFAULT_RUBRIC)
            self.assertEqual((case / "presentation-v1.pptx").read_bytes(), old)

    def test_confirmed_choice_new_version_and_resume_after_missing_deck(self):
        import subprocess
        import sys

        tools_dir = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as folder:
            case = Path(folder)
            def cli(script, *args):
                return subprocess.run([sys.executable, str(tools_dir / script), *map(str, args)],
                                      capture_output=True, text=True)
            state = json.loads((DEMO / "state.json").read_text())
            state.update(format_version=2, delivery_version=1, presentation="presentation-v1.pptx",
                         rubric="local-rubric.json")
            rubric = score.read_json(score.DEFAULT_RUBRIC)
            rubric["version"] += "-fixture"
            path = case / "state.json"
            path.write_text(json.dumps(state))
            (case / "local-rubric.json").write_text(json.dumps(rubric))
            assessments = score.read_json(DEMO / "scoring.json")
            assessments["rubric_version"] = rubric["version"]
            (case / "scoring.json").write_text(json.dumps(assessments))
            shutil.copy(DEMO / "evidence.md", case / "evidence.md")
            shutil.copy(DEMO / "presentation.json", case / "presentation-v1.json")
            first = cli("handoff.py", "build", case)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("awaiting_choice", cli("check.py", "state", path).stdout)

            # Ответ относится только к тесту с явно заданным диагностическим выбором.
            state.update(stage="strategy", delivery_version=2, presentation="presentation-v2.pptx",
                         decision={"option_id":"diagnose_both", "quote":"Учебный ответ: согласовать только общий срез."})
            path.write_text(json.dumps(state))
            fields = score.read_json(DEMO / "presentation.json")
            fields["slides"][0]["title"] = "Общий срез по двум аудиториям"
            (case / "presentation-v2.json").write_text(json.dumps(fields))
            second = cli("handoff.py", "build", case)
            self.assertEqual(second.returncode, 0, second.stderr)
            original = (case / "presentation-v2.pptx").read_bytes()
            self.assertNotEqual(original, (case / "presentation-v1.pptx").read_bytes())
            (case / "result.md").write_text("Учебное решение. Продукт и коммуникация измеряются в одном окне.")
            state.update(stage="complete", output="result.md")
            path.write_text(json.dumps(state))
            self.assertEqual(cli("check.py", "state", path).returncode, 0)
            (case / "presentation-v2.pptx").unlink()
            self.assertNotEqual(cli("check.py", "state", path).returncode, 0)
            snapshot = cli("status.py", case)
            self.assertEqual(snapshot.returncode, 0, snapshot.stderr)
            self.assertIn("diagnose_both", snapshot.stdout)
            repaired = cli("handoff.py", "repair", case)
            self.assertEqual(repaired.returncode, 0, repaired.stderr)
            self.assertEqual(original, (case / "presentation-v2.pptx").read_bytes())
            self.assertEqual(cli("check.py", "state", path).returncode, 0)

    def test_source_edit_and_stale_quote_in_quick_and_standard(self):
        for level in ("quick", "standard"):
            with self.subTest(level=level), tempfile.TemporaryDirectory() as tmp:
                case = Path(tmp)
                state = json.loads((DEMO / "state.json").read_text())
                state.update(format_version=2, delivery_version=1, level=level,
                             stage="complete", presentation="presentation-v1.pptx", output="result.md",
                             decision={"option_id":"diagnose_both", "quote":"Согласовать проверку."})
                path = case / "state.json"
                path.write_text(json.dumps(state))
                (case / "result.md").write_text("Итог учебного выбора")
                for n in ("scoring.json","evidence.md"):
                    shutil.copy(DEMO / n, case / n)
                shutil.copy(DEMO / "presentation.json", case / "presentation-v1.json")
                handoff.handoff(case,1,score.DEFAULT_RUBRIC)
                data = (case / "evidence.md").read_text()
                self.assertIn("500", data)
                (case / "evidence.md").write_text(data.replace("500","900",1))
                with self.assertRaisesRegex(ValueError,"basis-v1"):
                    check.check_state(path)
                with self.assertRaisesRegex(ValueError,"basis-v1"):
                    handoff.handoff(case,1,score.DEFAULT_RUBRIC,repair=True)
                (case / "evidence.md").write_text(data)
                state["decision"]["quote"] = "Дополнительно запросить данные."
                path.write_text(json.dumps(state))
                with self.assertRaisesRegex(ValueError,"executive-summary"):
                    check.check_state(path)

    def test_shipped_case_detects_changed_value_with_same_evidence_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / "case"
            shutil.copytree(DEMO.parent / "decision", case)
            evidence = case / "evidence.md"
            data = evidence.read_text()
            edited = "\n".join(line.replace("500","900") if line.startswith("| E6 |") else line
                               for line in data.split("\n"))
            self.assertNotEqual(data, edited)
            evidence.write_text(edited)
            with self.assertRaisesRegex(ValueError,"basis-v2"):
                handoff.handoff(case,2,score.DEFAULT_RUBRIC,verify=True)

    def test_executive_summary_matches_all_rows_and_keeps_untrusted_text_as_text(self):
        import executive
        from html.parser import HTMLParser
        class Tags(HTMLParser):
            def __init__(self):
                super().__init__()
                self.names = []
            def handle_starttag(self, tag, attrs):
                self.names.append(tag)
        state = score.read_json(DEMO / "state.json")
        inputs = handoff.assessments(DEMO, state, score.DEFAULT_RUBRIC)
        result = executive.render(DEMO, state, *inputs, 1)
        self.assertEqual(result, (DEMO / "executive-summary-v1.html").read_bytes())
        self.assertEqual(result.count(b"<tr>"), len(state["options"]) + 1)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "summary-v1.json").write_text('{"lead":"<script>alert(1)</script>"}')
            html = executive.render(root, state, *inputs, 1).decode()
            tags = Tags()
            tags.feed(html)
            self.assertNotIn("script", tags.names)
            self.assertIn("&lt;script&gt;", html)
            self.assertIn('>53<span class="gate">', html)
            self.assertIn("устойчивого лидера нет", html)
