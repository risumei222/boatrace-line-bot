import copy, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest_lab.build_dataset import build_backtest_dataset
from backtest_lab.run_backtest import BacktestIntegrityError, EngineSpec, format_backtest_summary, run_backtest

def _ds():
    b = {"parserVersion": "1.0.0", "encoding": "cp932", "races": [
        {"raceId": "20250101_01_01", "raceDate": "20250101", "venue": "桐生", "venueCode": "01", "raceNo": 1, "racers": [{"boatNumber": i, "rankClass": "A1" if i == 1 else "B1"} for i in range(1, 7)]},
        {"raceId": "20250101_01_02", "raceDate": "20250101", "venue": "桐生", "venueCode": "01", "raceNo": 2, "racers": [{"boatNumber": i, "rankClass": "B1"} for i in range(1, 7)]},
        {"raceId": "20250101_01_03", "raceDate": "20250101", "venue": "桐生", "venueCode": "01", "raceNo": 3, "racers": [{"boatNumber": i, "rankClass": "A1"} for i in range(1, 7)]},
    ]}
    k = {"resultParserVersion": "1.0.0", "sourceParserVersion": "1.0.0", "encoding": "cp932", "results": [
        {"raceId": "20250101_01_01", "raceDate": "20250101", "venue": "桐生", "venueCode": "01", "raceNo": 1, "resultStatus": "NORMAL", "hasAbnormal": False, "finishingOrder": [1, 2, 3], "racerOutcomes": [], "abnormalEntries": [], "refundBoatNos": [], "k0BoatNos": [], "sanrentan": [{"combination": "1-2-3", "payout": 850, "popularity": 2}], "unknownItems": []},
        {"raceId": "20250101_01_02", "raceDate": "20250101", "venue": "桐生", "venueCode": "01", "raceNo": 2, "resultStatus": "NORMAL", "hasAbnormal": False, "finishingOrder": [3, 1, 2], "racerOutcomes": [], "abnormalEntries": [], "refundBoatNos": [], "k0BoatNos": [], "sanrentan": [{"combination": "3-1-2", "payout": 2400, "popularity": 9}], "unknownItems": []},
        {"raceId": "20250101_01_03", "raceDate": "20250101", "venue": "桐生", "venueCode": "01", "raceNo": 3, "resultStatus": "ABNORMAL", "hasAbnormal": True, "finishingOrder": [1, 2, 3], "racerOutcomes": [], "abnormalEntries": [{"boatNumber": 4, "codeRaw": "F"}], "refundBoatNos": [4], "k0BoatNos": [], "sanrentan": [{"combination": "1-2-3", "payout": 500, "popularity": 1}], "unknownItems": []},
    ]}
    return build_backtest_dataset(b, k)

class TestRunBacktest(unittest.TestCase):
    def test_stub_abcd(self):
        rep = run_backtest(_ds())
        self.assertEqual([c["engineId"] for c in rep["engineComparison"]], ["A", "B", "C", "D"])
        for r in rep["engineComparison"]:
            self.assertEqual((r["totalRaces"], r["evaluableRaces"], r["nonEvaluableRaces"], r["skippedRaces"], r["betCount"]), (3, 2, 1, 3, 0))
            self.assertIsNone(r["recoveryRate"])

    def test_isolation(self):
        ds = _ds()
        orig = copy.deepcopy(ds)
        def spy(pin):
            self.assertNotIn("evaluation", pin)
            self.assertNotIn("sanrentan", pin)
            pin["racers"] = []
            return {"bets": []}
        run_backtest(ds, [EngineSpec("S", "Spy", "TEST", spy)])
        self.assertEqual(ds, orig)

    def test_aggregation_and_abnormal_exclusion(self):
        ds = _ds()
        m1_fn = lambda _: {"bets": [{"combination": "1-2-3", "stake": 100}, {"combination": "1-3-2", "stake": 100}]}
        m2_fn = lambda pin: {"bets": [{"combination": "1-2-3", "stake": 100}]} if pin["racers"][0].get("rankClass") == "A1" else {"bets": []}
        rep = run_backtest(ds, [EngineSpec("M1", "All", "TEST", m1_fn), EngineSpec("M2", "A1", "TEST", m2_fn)], include_race_logs=True)
        m1, m2 = rep["engines"]["M1"]["metrics"], rep["engines"]["M2"]["metrics"]
        self.assertEqual((m1["betCount"], m1["excludedAbnormalBetCount"], m1["hitCount"], m1["investmentAmount"], m1["payoutAmount"], m1["profit"]), (4, 2, 1, 400, 850, 450))
        self.assertEqual((m2["betCount"], m2["excludedAbnormalBetCount"], m2["hitCount"], m2["investmentAmount"], m2["payoutAmount"], m2["profit"]), (1, 1, 1, 100, 850, 750))
        self.assertIn("engineComparison", format_backtest_summary(rep))

    def test_bad_comb(self):
        with self.assertRaises(BacktestIntegrityError):
            run_backtest(_ds(), [EngineSpec("X", "Bad", "TEST", lambda _: {"bets": [{"combination": "1-2"}]})])

if __name__ == "__main__":
    unittest.main()
