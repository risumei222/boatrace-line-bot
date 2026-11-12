import sys,unittest,urllib.request,lhafile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from backtest_lab.parse_b import parse_b_bytes,parse_b_racer_row
from backtest_lab.parse_k_results import parse_k_results_bytes
def mk_row(boat=1,rid=4292,nw="5.96",beq="170",ser="46413       "):
 r=bytearray(b"1 4292"+"麻生慎介".encode("cp932")+b"40"+"広島".encode("cp932")+b"53A2 5.96 39.60 6.62 42.31  7 31.20170 38.46 46413       11");r[0:1]=str(boat).encode();r[2:6]=f"{rid:04d}".encode();r[25:29]=nw.encode();r[55:58]=beq.encode();r[65:77]=ser.encode();return bytes(r)
class TestBParser(unittest.TestCase):
    def test_row_and_anomalies(self):
        self.assertFalse(parse_b_racer_row(mk_row()[:-1], 10)["valid"])
        p = parse_b_racer_row(mk_row(nw="----", beq=" 12", ser="4F12S       "), 11)
        self.assertIsNone(p["nationalWinRate"])
        self.assertIsNone(p["boatEquipmentNo"])
        self.assertEqual(p["currentSeriesResultsRaw"], "4F12S       ")
        for f in ("national3Rate", "local3Rate", "avgSt", "fCount", "lCount"):
            self.assertNotIn(f, p)
        ls = [b"STARTB", b"21BBGN", "   第　４日          ２０２５年１１月１２日                  ボートレース芦　屋".encode("cp932"), "　１Ｒ  予選                  Ｈ１８００ｍ  電話投票締切予定０８：３５ ".encode("cp932"), mk_row(1, 4001), mk_row(1, 4002), b"21BEND"]
        ts = {a["type"] for a in parse_b_bytes(b"\r\n".join(ls))["anomalies"]}
        self.assertIn("RACER_COUNT_NOT_SIX", ts)
        self.assertIn("DUPLICATE_BOAT_NO", ts)

    def test_official_b_and_k_join(self):
        for u, p in [("https://www1.mbrace.or.jp/od2/B/202511/b251112.lzh", "/tmp/b251112_v.lzh"), ("https://www1.mbrace.or.jp/od2/B/202611/b261110.lzh", "/tmp/b261110_v.lzh")]:
            urllib.request.urlretrieve(u, p)
        ld = lambda p: lhafile.Lhafile(p).read(lhafile.Lhafile(p).infolist()[0].filename)
        b25 = parse_b_bytes(ld("/tmp/b251112_v.lzh"))
        self.assertEqual((b25["venueCount"], b25["raceCount"], b25["anomalyCount"]), (9, 108, 0))
        a1 = [r for r in b25["races"] if r["raceId"] == "20251112_21_01"][0]
        a2 = [r for r in b25["races"] if r["raceId"] == "20251112_21_02"][0]
        self.assertEqual((len(a1["racers"]), len(a2["racers"])), (6, 6))
        self.assertEqual((a1["racers"][0]["racerId"], a1["racers"][0]["nationalWinRate"], a2["racers"][0]["racerId"]), ("4292", 5.96, "3833"))
        b26 = parse_b_bytes(ld("/tmp/b261110_v.lzh"))
        self.assertEqual((b26["venueCount"], b26["raceCount"], b26["anomalyCount"]), (13, 156, 0))
        f1 = [r for r in b26["races"] if r["raceId"] == "20261110_22_01"][0]
        f2 = [r for r in b26["races"] if r["raceId"] == "20261110_22_02"][0]
        self.assertEqual((len(f1["racers"]), len(f2["racers"])), (6, 6))
        self.assertEqual((f1["racers"][0]["racerId"], f1["racers"][0]["nationalWinRate"], f2["racers"][0]["racerId"]), ("3876", 7.22, "4045"))
        self.assertEqual({r["raceId"] for r in b25["races"]}, {r["raceId"] for r in parse_k_results_bytes(ld("/tmp/k251112.lzh"))["results"]})
        self.assertEqual({r["raceId"] for r in b26["races"]}, {r["raceId"] for r in parse_k_results_bytes(ld("/tmp/k261110.lzh"))["results"]})

if __name__ == "__main__":
    unittest.main()
