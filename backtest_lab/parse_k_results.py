from __future__ import annotations
import json,re
from pathlib import Path
from typing import Any
from backtest_lab.parse_k import parse_k_bytes

PRE=b"        \x82\x52\x98\x41\x92\x50"
POP=b"\x90\x6c\x8b\x43"
COMB_RE=re.compile(r"^[1-6]-[1-6]-[1-6]$")
DIG_RE=re.compile(r"^\d+$")

def parse_sanrentan_payout_line(line:bytes,line_number:int|None=None)->dict[str,Any]|None:
 if len(line)!=44 or line[0:14]!=PRE:return None
 c=line[17:22].decode("ascii","replace").strip()
 p=line[22:31].decode("ascii","replace").strip()
 k=line[37:43].decode("ascii","replace").strip()
 vc=bool(COMB_RE.fullmatch(c))
 vp=bool(DIG_RE.fullmatch(p))
 vk=line[33:37]==POP and bool(DIG_RE.fullmatch(k))
 ok=vc and vp and vk
 return {"status":"CONFIRMED" if ok else "UNKNOWN","lineNumber":line_number,"byteLength":44,"combination":c if vc else None,"combinationRaw":line[17:22].decode("ascii","replace"),"payout":int(p) if vp else None,"payoutRaw":line[22:31].decode("ascii","replace"),"popularity":int(k) if vk else None,"popularityRaw":line[37:43].decode("ascii","replace"),"rawHex":line.hex()}

def classify_rank_raw(r:str)->str:
 if r in("01","02","03","04","05","06"):return "NORMAL"
 if r=="F":return "REFUND_F"
 if r=="K0":return "K0_RECORDED"
 if r in("S0","S1","S2"):return "RAW_UNINTERPRETED"
 return "UNKNOWN"

def parse_k_results_bytes(raw_bytes:bytes)->dict[str,Any]:
 base=parse_k_bytes(raw_bytes)
 res=[]
 for rc in base["races"]:
  fin,out,abn,ref,k0,unk=[],[],[],[],[],[]
  for r in rc["racers"]:
   cd,bt,id_=r["rankRaw"],r["boatNo"],r["racerNo"]
   cl=classify_rank_raw(cd)
   out.append({"lineNumber":r["lineNumber"],"rankRaw":cd,"rank":r["rank"],"boatNumber":bt,"racerId":id_,"classification":cl,"rawHex":r["rawHex"]})
   if cl=="NORMAL":fin.append({"rank":r["rank"],"rankRaw":cd,"boatNumber":bt,"racerId":id_})
   else:
    abn.append({"codeRaw":cd,"boatNumber":bt,"racerId":id_,"classification":cl,"lineNumber":r["lineNumber"]})
    if cl=="REFUND_F":ref.append(bt)
    elif cl=="K0_RECORDED":k0.append(bt)
    elif cl=="UNKNOWN":unk.append({"type":"UNKNOWN_RANK_CODE","codeRaw":cd,"boatNumber":bt,"racerId":id_,"lineNumber":r["lineNumber"]})
  fin.sort(key=lambda x:x["rank"])
  hits=[x for o in rc["otherLines"] for x in[parse_sanrentan_payout_line(bytes.fromhex(o["rawHex"]),o["lineNumber"])] if x]
  if len(hits)==1:
   sr=hits[0]
   if sr["status"]=="UNKNOWN":unk.append({"type":"UNKNOWN_SANRENTAN_FORMAT","lineNumber":sr["lineNumber"],"rawHex":sr["rawHex"]})
  else:
   sr={"status":"UNKNOWN","lineNumber":hits[0]["lineNumber"] if hits else None,"byteLength":None,"combination":None,"combinationRaw":None,"payout":None,"payoutRaw":None,"popularity":None,"popularityRaw":None,"rawHex":None}
   unk.append({"type":"MISSING_OR_MULTIPLE_SANRENTAN","raceId":rc["raceId"],"count":len(hits)})
  ha=len(abn)>0
  st="UNKNOWN" if unk else("ABNORMAL" if ha else "NORMAL")
  res.append({"raceId":rc["raceId"],"raceDate":rc["raceDate"],"venue":rc["venue"],"venueCode":rc["venueCode"],"raceNo":rc["raceNo"],"resultStatus":st,"hasAbnormal":ha,"finishingOrder":fin,"racerOutcomes":out,"abnormalEntries":abn,"refundBoatNos":sorted(ref),"k0BoatNos":sorted(k0),"sanrentan":sr,"unknownItems":unk})
 return {"resultParserVersion":"1.0.0","sourceParserVersion":base["parserVersion"],"encoding":"CP932","raceCount":len(res),"abnormalRaceCount":sum(1 for x in res if x["hasAbnormal"]),"unknownRaceCount":sum(1 for x in res if x["resultStatus"]=="UNKNOWN"),"results":res}

def parse_k_results_file(input_path:str|Path,output_path:str|Path)->dict[str,Any]:
 d=parse_k_results_bytes(Path(input_path).read_bytes())
 o=Path(output_path)
 o.parent.mkdir(parents=True,exist_ok=True)
 o.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
 return d
