import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from follow_up import report

DEMO = Path(__file__).resolve().parents[1] / "demo/family/first-run"


class FollowUpTests(unittest.TestCase):
    def test_due_date_and_evidence_limit_what_needs_attention(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp)
            for n in ("scoring.json", "evidence.md"):
                shutil.copy(DEMO / n, case / n)
            entry = dict(id="scope", owner="Аналитик", action="Сверить данные", metric="поток", review_if="малый поток", evidence=["E6"], status="open")
            items = [dict(entry, due="2026-11-20"), dict(entry, id="next", due=None),
                     dict(entry, id="ended", due="2026-11-20", status="done")]
            (case / "commitments.json").write_text(json.dumps({"items": items}))
            out = "\n".join(report(case, ["E6"], date(2026, 11, 22)))
            self.assertIn("family_signal / criteria / economics", out)
            self.assertEqual(out.count("просрочено"), 1)
            self.assertIn("уточнить срок", out)
            self.assertNotIn("Аналитик", "\n".join(report(case, ["E2"], date(2026, 11, 22))))
            with self.assertRaises(ValueError):
                report(case, ["E999"], date(2026, 11, 22))
