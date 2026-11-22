import csv
import io
import json
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import check
import deck
import handoff
import investment
import investment_model
import score

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "demo/workshop/investment"


class InvestmentTests(unittest.TestCase):
    def test_second_domain_new_case_build_verify_and_incomplete_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp)
            for name in ("state.json", "scoring.json", "evidence.md"):
                shutil.copy(LIBRARY / name, case / name)
            path = case / "presentation-v1.json"
            state = json.loads((case / "state.json").read_text())
            handoff.prepare(case, state, score.DEFAULT_RUBRIC, 1)
            empty = json.loads(path.read_text())
            self.assertIn("investment", empty)
            self.assertEqual(empty["finance_input"],"finance-v1.csv")
            self.assertTrue((case / "finance-v1.csv").is_file())
            spec=json.loads((LIBRARY / path.name).read_text())
            path.write_text(json.dumps(spec,ensure_ascii=False))
            with self.assertRaisesRegex(ValueError, "источник|числовые"):
                handoff.handoff(case,1,score.DEFAULT_RUBRIC)
            shutil.copy(LIBRARY / "finance-v1.csv",case / "finance-v1.csv")
            outputs=handoff.handoff(case,1,score.DEFAULT_RUBRIC)
            for artifact,_ in outputs:
                self.assertEqual(artifact.read_bytes(),(LIBRARY/artifact.name).read_bytes())
            handoff.handoff(case,1,score.DEFAULT_RUBRIC,verify=True)
            (case/"investment-model-v1.xlsx").unlink()
            with self.assertRaisesRegex(ValueError,"investment-model"):
                check.check_state(case/"state.json")
            handoff.handoff(case,1,score.DEFAULT_RUBRIC,repair=True)
            del spec["finance_input"]
            path.write_text(json.dumps(spec))
            with self.assertRaisesRegex(ValueError,"finance_input"):
                handoff.handoff(case,1,score.DEFAULT_RUBRIC,verify=True)
            path.unlink()
            with self.assertRaisesRegex(ValueError,"presentation-v1.json"):
                handoff.handoff(case,1,score.DEFAULT_RUBRIC,repair=True)

    def test_signed_effect_and_missing_period(self):
        with (LIBRARY/"finance-v1.csv").open() as f:
            records=list(csv.DictReader(f))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"model.csv"
            def save(rows):
                with path.open("w") as f:
                    writer=csv.DictWriter(f,fieldnames=investment_model.FIELDS)
                    writer.writeheader()
                    writer.writerows(rows)
            records[0]["additional_per_unit"]="-1"
            save(records)
            with ZipFile(io.BytesIO(investment_model.render(path,["reminders","queue_offer"]))) as book:
                sheet=ET.fromstring(book.read("xl/worksheets/sheet2.xml"))
                cell=sheet.find(".//{*}c[@r='L2']")
                self.assertEqual(cell.find("{*}f").text,"K2-H2")
                self.assertEqual(float(cell.find("{*}v").text),-2400)
            save(records[:-1])
            with self.assertRaisesRegex(ValueError,"периоды"):
                investment_model.render(path,None)

    def test_deck_rejects_missing_sources_and_misleading_agenda(self):
        spec=json.loads((LIBRARY/"presentation-v1.json").read_text())
        pack=deepcopy(spec["investment"])
        pack["pages"][6]["refs"]=["missing"]
        with self.assertRaisesRegex(ValueError,"источники"):
            investment.checked(pack)
        pack=deepcopy(spec["investment"])
        pack["agenda"][1]["from"]+=1
        with self.assertRaisesRegex(ValueError,"Диапазоны"):
            investment.checked(pack)
        spec["investment"]["core_text"]={"2":{"valueA":"100 / 100"}}
        with self.assertRaisesRegex(ValueError,"Баллы"):
            deck.render(spec)
