import sys,unittest,lhafile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from backtest_lab.parse_k_results import parse_k_results_bytes,parse_sanrentan_payout_line
from backtest_lab.test_k_parser import make_race_header,make_racer_row

def mk_sr(c,p,k):
 r=bytearray(b" "*44)
 r[8:14]=b"\x82\x52\x98\x41\x92\x50"
 r[17:22]=c.encode("ascii")
 r[22:31]=f"{p:>9d}".encode("ascii")
 r[33:37]=b"\x90\x6c\x8b\x43"
 r[37:43]=f"{k:>6d}".encode("ascii")
 return bytes(r)

class TestKResults(unittest.TestCase):
 def test_summary_and_unknown(self):
  self.assertIsNone(parse_sanrentan_payout_line("   [払戻金]       ３連単           ３連複           ２連単         ２連複".encode("cp932"),13))
  self.assertIsNone(parse_sanrentan_payout_line("           1R  1-5-3    2250    1-3-5     840    1-5     370    1-5     440".encode("cp932"),14))
  b=bytearray(b" "*44);b[8:14]=b"\x82\x52\x98\x41\x92\x50";b[17:22]=b"-----"
  self.assertEqual(parse_sanrentan_payout_line(bytes(b),99)["status"],"UNKNOWN")
 def test_codes_and_l0(self):
  ls=["第 1日 2025/11/12 ボートレース芦屋".encode("cp932"),make_race_header(1,1800),make_racer_row(1,4001,1,"01"),make_racer_row(2,4002,2,"02"),make_racer_row(3,4003,3,"S0"),make_racer_row(4,4004,4,"S1"),make_racer_row(5,5101,None,"K0"),make_racer_row(6,4006,6,"L0"),b"",mk_sr("1-2-3",500,1)]
  r=parse_k_results_bytes(b"\r\n".join(ls))["results"][0]
  self.assertEqual(r["resultStatus"],"UNKNOWN")
  self.assertEqual(r["k0BoatNos"],[5])
  self.assertEqual({x["boatNumber"]:x["codeRaw"] for x in r["abnormalEntries"]},{3:"S0",4:"S1",5:"K0",6:"L0"})
 def test_official(self):
  ld=lambda p:lhafile.Lhafile(p).read([i.filename for i in lhafile.Lhafile(p).infolist() if i.filename.lower().endswith(".txt")][0])
  r26=parse_k_results_bytes(ld("/tmp/k261110.lzh"))
  f1=[r for r in r26["results"] if r["raceId"]=="20261110_22_01"][0]
  self.assertEqual((f1["sanrentan"]["combination"],f1["sanrentan"]["payout"],f1["sanrentan"]["popularity"]),("1-3-2",930,4))
  r25=parse_k_results_bytes(ld("/tmp/k251112.lzh"))
  a1=[r for r in r25["results"] if r["raceId"]=="20251112_21_01"][0]
  self.assertEqual((a1["sanrentan"]["combination"],a1["sanrentan"]["payout"],a1["sanrentan"]["popularity"]),("1-5-3",2250,9))
  fr=[r for r in r25["results"] if r["refundBoatNos"]==[3,4]][0]
  self.assertEqual(fr["sanrentan"]["combination"],"5-1-6")
  kr=[r for r in r25["results"] if 5 in r["k0BoatNos"]][0]
  self.assertTrue(any(e["codeRaw"]=="K0" and e["boatNumber"]==5 for e in kr["abnormalEntries"]))
  for r in r26["results"]+r25["results"]:
   if r["sanrentan"]["status"]=="CONFIRMED":self.assertEqual(r["sanrentan"]["byteLength"],44)

if __name__=="__main__":unittest.main()
