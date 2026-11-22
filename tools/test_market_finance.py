import csv
import importlib.util
import unittest
from decimal import Decimal
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[1] / "analysis" / "market-finance"
spec = importlib.util.spec_from_file_location("operator_finance", FOLDER / "model.py")
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


class ForecastTests(unittest.TestCase):
    def setUp(self):
        with (FOLDER / "scenarios.csv").open(encoding="utf-8") as f:
            self.row = next(csv.DictReader(f))

    def test_year_ends_before_last_two_quarters_of_latest_cohorts(self):
        weekly, threshold, quarters = model.forecast(self.row, 6_000_000)
        self.assertEqual((weekly, threshold), (450, 14_000))
        self.assertEqual([q[0] for q in quarters], [0, 1170, 2808, 4212])
        self.assertEqual(quarters[-1][-1].quantize(Decimal("0.01")), 1_595_000)
        self.assertLess(quarters[2][-1], 0)

    def test_harm_in_a_pilot_and_first_case_deduplication(self):
        self.row.update(months_q0="-0.1", months_q1="0", months_q2="0")
        self.assertLess(model.forecast(self.row, 6_000_000)[2][1][0], 0)
        self.row["first_risk_share_week"] = "0.5"
        with self.assertRaisesRegex(ValueError, "базу"):
            model.forecast(self.row, 6_000_000)

    def test_threshold_with_fractional_month_and_alternate_revenue(self):
        self.assertEqual(model.required_months(6_000_000, 0, 0), 12_000)
        self.assertEqual(model.required_months(6_000_000, 1_000_001, 0), 14_001)
        self.assertEqual(model.required_months(6_000_000, 0, 7_000_000), 0)
