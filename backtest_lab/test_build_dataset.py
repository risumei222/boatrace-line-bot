import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest_lab.build_dataset import (
    DataLeakError,
    DatasetBuildError,
    FORBIDDEN_PREDICTION_KEYS,
    build_backtest_dataset,
)


def _collect_keys(obj):
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _collect_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _collect_keys(item)
    return keys


class TestBuildDataset(unittest.TestCase):
    def setUp(self):
        self.sample_b = {
            "parserVersion": "1.0.0",
            "encoding": "cp932",
            "races": [
                {
                    "raceId": "20250101_01_01",
                    "raceDate": "20250101",
                    "venue": "桐生",
                    "venueCode": "01",
                    "raceNo": 1,
                    "raceName": "予選",
                    "distance": 1800,
                    "deadline": "15:20",
                    "headerLineNumber": 10,
                    "headerRawHex": "3152",
                    "racers": [
                        {
                            "boatNumber": 1,
                            "racerId": "4001",
                            "racerName": "選手A",
                            "rankClass": "A1",
                            "weight": 52.0,
                            "nationalWinRate": 6.50,
                            "national2Rate": 45.0,
                            "localWinRate": 6.10,
                            "local2Rate": 40.0,
                            "motorNo": 12,
                            "motor2Rate": 38.5,
                            "boatNo": 34,
                            "boat2Rate": 35.0,
                            "currentSeriesResults": None,  # Missing intentionally
                        }
                    ],
                }
            ],
        }
        self.sample_k = {
            "resultParserVersion": "1.0.0",
            "sourceParserVersion": "1.0.0",
            "encoding": "cp932",
            "results": [
                {
                    "raceId": "20250101_01_01",
                    "raceDate": "20250101",
                    "venue": "桐生",
                    "venueCode": "01",
                    "raceNo": 1,
                    "resultStatus": "ABNORMAL",
                    "hasAbnormal": True,
                    "finishingOrder": [1, 2, 3],
                    "racerOutcomes": [
                        {
                            "boatNumber": 1,
                            "rank": 1,
                            "actualCourse": 1,
                            "actualSt": 0.12,
                            "classification": "NORMAL",
                        },
                        {
                            "boatNumber": 4,
                            "rank": None,
                            "actualCourse": 4,
                            "actualSt": -0.02,
                            "classification": "REFUND_F",
                        },
                    ],
                    "abnormalEntries": [{"boatNumber": 4, "codeRaw": "F"}],
                    "refundBoatNos": [4],
                    "k0BoatNos": [],
                    "sanrentan": [{"combination": "1-2-3", "payout": 1250, "popularity": 3}],
                    "unknownItems": [],
                }
            ],
        }

    def test_prediction_input_has_no_post_race_fields(self):
        ds = build_backtest_dataset(self.sample_b, self.sample_k)
        self.assertEqual(ds["recordCount"], 1)
        pred = ds["records"][0]["prediction_input"]
        all_pred_keys = _collect_keys(pred)
        leaked = all_pred_keys & FORBIDDEN_PREDICTION_KEYS
        self.assertEqual(leaked, set(), f"Leaked keys found in prediction_input: {leaked}")
        self.assertEqual(pred["unverifiedPreRace"]["exhibition"], "UNKNOWN")
        self.assertEqual(pred["unverifiedPreRace"]["weather"], "UNKNOWN")

    def test_evaluation_retains_post_race_results(self):
        ds = build_backtest_dataset(self.sample_b, self.sample_k)
        ev = ds["records"][0]["evaluation"]
        self.assertEqual(ev["resultStatus"], "ABNORMAL")
        self.assertEqual(ev["finishingOrder"], [1, 2, 3])
        self.assertEqual(ev["sanrentan"][0]["payout"], 1250)
        self.assertEqual(ev["sanrentan"][0]["popularity"], 3)
        self.assertEqual(ev["racerOutcomes"][0]["actualSt"], 0.12)
        self.assertEqual(ev["racerOutcomes"][0]["actualCourse"], 1)
        self.assertEqual(ev["refundBoatNos"], [4])

    def test_race_id_mismatch_raises_join_error(self):
        bad_k = copy.deepcopy(self.sample_k)
        bad_k["results"][0]["raceId"] = "20250101_01_02"
        with self.assertRaises(DatasetBuildError):
            build_backtest_dataset(self.sample_b, bad_k)

    def test_missing_and_abnormal_data_not_imputed(self):
        orig_b = copy.deepcopy(self.sample_b)
        orig_k = copy.deepcopy(self.sample_k)
        ds = build_backtest_dataset(self.sample_b, self.sample_k)
        # Raw inputs must remain completely unmutated
        self.assertEqual(self.sample_b, orig_b)
        self.assertEqual(self.sample_k, orig_k)
        # Missing values stay None (no imputation)
        racer = ds["records"][0]["prediction_input"]["racers"][0]
        self.assertIsNone(racer["currentSeriesResults"])
        outcome_f = ds["records"][0]["evaluation"]["racerOutcomes"][1]
        self.assertIsNone(outcome_f["rank"])
        self.assertEqual(outcome_f["classification"], "REFUND_F")

    def test_same_day_k_data_blocked_from_historical_context(self):
        with self.assertRaises(DataLeakError):
            build_backtest_dataset(
                self.sample_b,
                self.sample_k,
                historical_k_list=[self.sample_k],
            )

    def test_prior_day_k_data_allowed(self):
        prior_k = copy.deepcopy(self.sample_k)
        prior_k["results"][0]["raceDate"] = "20241231"
        ds = build_backtest_dataset(
            self.sample_b,
            self.sample_k,
            historical_k_list=[prior_k],
        )
        self.assertEqual(
            ds["records"][0]["prediction_input"]["historicalFeatures"]["validatedPriorKDates"],
            ["20241231"],
        )


if __name__ == "__main__":
    unittest.main()
