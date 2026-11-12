import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest_lab.join_bk import join_b_and_k

class TestJoinBK(unittest.TestCase):
    def test_join_matched_and_missing(self):
        b_data = {"races": [{"raceId": "20250101_01_01", "racers": [{"boatNumber": 1}]}, {"raceId": "20250101_01_02", "racers": []}]}
        k_data = {"results": [{"raceId": "20250101_01_01", "resultStatus": "NORMAL", "sanrentan": [{"combination": "1-2-3", "payout": 1250}]}, {"raceId": "20250101_01_03", "resultStatus": "NORMAL", "sanrentan": []}]}
        out = join_b_and_k(b_data, k_data)
        self.assertEqual(out["joinedCount"], 1)
        self.assertEqual(out["missingBIds"], ["20250101_01_03"])
        self.assertEqual(out["missingKIds"], ["20250101_01_02"])
        self.assertEqual(out["races"][0]["sanrentan"][0]["payout"], 1250)

if __name__ == "__main__":
    unittest.main()
