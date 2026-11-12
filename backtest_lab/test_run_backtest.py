import copy, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest_lab.build_dataset import build_backtest_dataset
from backtest_lab.run_backtest import BacktestIntegrityError, EngineSpec, format_backtest_summary, run_backtest

def _make_rec(rid, st="NORMAL", abn=False, abn_ent=None, ref=None, k0=None, san=None):
    b = {"parserVersion": "1.0.0", "encoding": "cp932", "races": [
        {"raceId": rid, "raceDate": "20250101", "venue": "桐生", "venueCode": "01", "raceNo": 1, "racers": [{"boatNumber": i, "rankClass": "A1" if i == 1 else "B1"} for i in range(1, 7)]}
    ]}
    k = {"resultParserVersion": "1.0.0", "sourceParserVersion": "1.0.0", "encoding": "cp932", "results": [
        {"raceId": rid, "raceDate": "20250101", "venue": "桐生", "venueCode": "01", "raceNo": 1,
         "resultStatus": st, "hasAbnormal": abn, "finishingOrder": [1, 2, 3], "racerOutcomes": [],
         "abnormalEntries": abn_ent or [], "refundBoatNos": ref or [], "k0BoatNos": k0 or [],
         "sanrentan": san, "unknownItems": []}
    ]}
    return build_backtest_dataset(b, k)["records"][0]

def _ds():
    return {
        "datasetBuilderVersion": "1.0.0",
        "records": [
            # 1: Normal with official dict sanrentan
            _make_rec("20250101_01_01", san={"combination": "1-2-3", "payout": 850, "popularity": 2}),
            # 2: Normal with list sanrentan (compatibility)
            _make_rec("20250101_01_02", san=[{"combination": "3-1-2", "payout": 2400, "popularity": 9}]),
            # 3: Abnormal (S2 / refund)
            _make_rec("20250101_01_03", st="ABNORMAL", abn=True, abn_ent=[{"boatNumber": 4, "codeRaw": "S2"}], ref=[4], san={"combination": "1-2-3", "payout": 500}),
            # 4: Abnormal (K0 absent)
            _make_rec("20250101_01_04", st="ABNORMAL", abn=True, abn_ent=[{"boatNumber": 2, "codeRaw": "K0"}], k0=[2], san={"combination": "1-2-3", "payout": 600}),
        ],
    }

class TestRunBacktest(unittest.TestCase):
    def test_stub_abcd_dict_and_list(self):
        rep = run_backtest(_ds())
        self.assertEqual([c["engineId"] for c in rep["engineComparison"]], ["A", "B", "C", "D"])
        for r in rep["engineComparison"]:
            self.assertEqual((r["totalRaces"], r["evaluableRaces"], r["nonEvaluableRaces"], r["skippedRaces"], r["betCount"]), (4, 2, 2, 4, 0))
            self.assertIsNone(r["recoveryRate"])

    def test_sanrentan_edge_cases_not_imputed(self):
        ds = {
            "datasetBuilderVersion": "1.0.0",
            "records": [
                _make_rec("R_NONE", san=None),
                _make_rec("R_BAD_COMB", san={"combination": "1-2", "payout": 500}),
                _make_rec("R_NEG_PAY", san={"combination": "1-2-3", "payout": -100}),
                _make_rec("R_STR_PAY", san={"combination": "1-2-3", "payout": "850"}),
                _make_rec("R_BOOL_PAY", san={"combination": "1-2-3", "payout": True}),
            ],
        }
        rep = run_backtest(ds)
        m = rep["engines"]["A"]["metrics"]
        self.assertEqual((m["totalRaces"], m["evaluableRaces"], m["nonEvaluableRaces"]), (5, 0, 5))

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
        m1_fn = lambda _: {"bets": [{"combination": "1-2-3", "stake": 100}, {"combination": "3-1-2", "stake": 100}]}
        rep = run_backtest(ds, [EngineSpec("M1", "All", "TEST", m1_fn)], include_race_logs=True)
        m1 = rep["engines"]["M1"]["metrics"]
        self.assertEqual((m1["evaluableRaces"], m1["nonEvaluableRaces"], m1["betCount"], m1["excludedAbnormalBetCount"], m1["hitCount"], m1["investmentAmount"], m1["payoutAmount"], m1["profit"]), (2, 2, 4, 4, 2, 400, 3250, 2850))
        self.assertIn("engineComparison", format_backtest_summary(rep))

    def test_bad_bet_comb(self):
        with self.assertRaises(BacktestIntegrityError):
            run_backtest(_ds(), [EngineSpec("X", "Bad", "TEST", lambda _: {"bets": [{"combination": "1-2"}]})])

if __name__ == "__main__":
    unittest.main()


class TestEvaluationMathVerification(unittest.TestCase):
    def test_payout_scaling_and_zero_cases(self):
        # Verify 100-yen unit payout scaling (200 yen & 300 yen stakes), zero-hit, zero-bet, zero-payout
        ds = {
            "datasetBuilderVersion": "1.0.0",
            "records": [
                _make_rec("R1", san={"combination": "1-2-3", "payout": 1250, "popularity": 4}),
                _make_rec("R2", san={"combination": "2-1-3", "payout": 3400, "popularity": 12}),
                _make_rec("R3", san={"combination": "4-5-6", "payout": 0, "popularity": 1}),
            ],
        }
        # Harness-only fixed dummy bets (NOT A/B/C/D)
        def fixed_dummy_harness(pin):
            rid = pin["raceId"]
            if rid == "R1":
                # 2 bets: 1-2-3 (200 yen -> 1250*2 = 2500), 1-3-2 (100 yen -> miss)
                return {"bets": [{"combination": "1-2-3", "stake": 200}, {"combination": "1-3-2", "stake": 100}]}
            if rid == "R2":
                # 1 bet: 1-2-3 (300 yen -> miss)
                return {"bets": [{"combination": "1-2-3", "stake": 300}]}
            # R3: zero bets (skip)
            return {"bets": []}

        rep = run_backtest(ds, [EngineSpec("VERIFY_MATH", "VerifyOnly", "TEST", fixed_dummy_harness)])
        m = rep["engines"]["VERIFY_MATH"]["metrics"]
        # Total stake = 300 + 300 + 0 = 600; Payout = 2500; Profit = +1900; Hit rate = 1/3
        self.assertEqual(m["totalRaces"], 3)
        self.assertEqual(m["evaluableRaces"], 3)
        self.assertEqual(m["skippedRaces"], 1)
        self.assertEqual(m["betRaces"], 2)
        self.assertEqual(m["betCount"], 3)
        self.assertEqual(m["hitCount"], 1)
        self.assertEqual(m["hitRaces"], 1)
        self.assertEqual(m["hitRatePerBet"], round(1 / 3, 6))
        self.assertEqual(m["hitRatePerBetRace"], 0.5)
        self.assertEqual(m["investmentAmount"], 600)
        self.assertEqual(m["payoutAmount"], 2500)
        self.assertEqual(m["recoveryRate"], round(2500 / 600, 6))
        self.assertEqual(m["profit"], 1900)

    def test_zero_hits_and_zero_payout_race(self):
        ds = {
            "datasetBuilderVersion": "1.0.0",
            "records": [
                _make_rec("R1", san={"combination": "1-2-3", "payout": 0}),
                _make_rec("R2", san={"combination": "2-3-4", "payout": 5000}),
            ],
        }
        # Bets 1-2-3 (0 payout) on R1 and 1-2-3 (miss) on R2
        fn = lambda _: {"bets": [{"combination": "1-2-3", "stake": 100}]}
        rep = run_backtest(ds, [EngineSpec("ZERO_OUT", "VerifyOnly", "TEST", fn)])
        m = rep["engines"]["ZERO_OUT"]["metrics"]
        self.assertEqual(m["betCount"], 2)
        self.assertEqual(m["hitCount"], 1)
        self.assertEqual(m["investmentAmount"], 200)
        self.assertEqual(m["payoutAmount"], 0)
        self.assertEqual(m["recoveryRate"], 0.0)
        self.assertEqual(m["profit"], -200)

        # All misses case
        miss_fn = lambda _: {"bets": [{"combination": "6-5-4", "stake": 100}]}
        rep_miss = run_backtest(ds, [EngineSpec("ALL_MISS", "VerifyOnly", "TEST", miss_fn)])
        mm = rep_miss["engines"]["ALL_MISS"]["metrics"]
        self.assertEqual((mm["hitCount"], mm["hitRatePerBet"], mm["payoutAmount"], mm["recoveryRate"], mm["profit"]), (0, 0.0, 0, 0.0, -200))
