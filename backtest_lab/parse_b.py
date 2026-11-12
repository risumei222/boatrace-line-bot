from __future__ import annotations
import json, re
from datetime import datetime
from pathlib import Path
from typing import Any

ZEN = str.maketrans("０１２３４５６７８９：ＲＨｍ", "0123456789:RHm")
BBGN_RE = re.compile(rb"^(\d{2})BBGN$")
BEND_RE = re.compile(rb"^(\d{2})BEND$")
VENUE_RE = re.compile(r"第\s*(\d+)日\s+(\d{4})年(\d{2})月(\d{2})日\s+ボートレース(.+)$")
RACE_RE = re.compile(r"^\s*(\d{1,2})R\s+(.+?)\s+H(\d+)m\s+電話投票締切予定(\d{2}:\d{2})\s*$")
CAND_RE = re.compile(rb"^[1-6] \d{4}")
DEC_RE = re.compile(r"^\d+\.\d+$")
INT_RE = re.compile(r"^\d+$")

def dec(b: bytes) -> str:
    return b.decode("cp932", errors="replace")

def p_flt(raw: str, fld: str, unk: list[str]) -> float | None:
    v = raw.strip()
    if DEC_RE.fullmatch(v): return float(v)
    unk.append(fld); return None

def p_int(raw: str, fld: str, unk: list[str], blank: bool = False) -> int | None:
    v = raw.strip()
    if not v and blank: return None
    if INT_RE.fullmatch(v): return int(v)
    unk.append(fld); return None

def p_beq(raw: str, unk: list[str]) -> int | None:
    if len(raw) == 3 and raw.isdigit(): return int(raw)
    unk.append("boatEquipmentNo"); return None

def parse_b_racer_row(line: bytes, line_number: int | None = None) -> dict[str, Any] | None:
    if not CAND_RE.match(line): return None
    if len(line) != 79:
        return {"valid": False, "lineNumber": line_number, "byteLength": len(line), "rawHex": line.hex()}
    unk: list[str] = []
    nm = dec(line[6:14]); ag = line[14:16].decode("ascii", "replace"); br = dec(line[16:20])
    wt = line[20:22].decode("ascii", "replace"); cl = line[22:24].decode("ascii", "replace").strip()
    nw = line[25:29].decode("ascii", "replace"); n2 = line[30:35].decode("ascii", "replace")
    lw = line[36:40].decode("ascii", "replace"); l2 = line[41:46].decode("ascii", "replace")
    mn = line[47:49].decode("ascii", "replace"); m2 = line[50:55].decode("ascii", "replace")
    bq = line[55:58].decode("ascii", "replace"); b2 = line[59:64].decode("ascii", "replace")
    sr = line[65:77].decode("ascii", "replace"); hy = line[77:79].decode("ascii", "replace")
    return {"valid": True, "lineNumber": line_number, "byteLength": 79, "boatNo": int(line[0:1]), "racerId": line[2:6].decode("ascii"), "racerName": nm.replace("\u3000", " ").strip(), "racerNameRaw": nm, "age": p_int(ag, "age", unk), "ageRaw": ag, "branch": br.replace("\u3000", " ").strip(), "branchRaw": br, "weight": p_int(wt, "weight", unk), "weightRaw": wt, "racerClass": cl if cl in ("A1", "A2", "B1", "B2") else None, "racerClassRaw": cl, "nationalWinRate": p_flt(nw, "nationalWinRate", unk), "nationalWinRateRaw": nw, "national2Rate": p_flt(n2, "national2Rate", unk), "national2RateRaw": n2, "localWinRate": p_flt(lw, "localWinRate", unk), "localWinRateRaw": lw, "local2Rate": p_flt(l2, "local2Rate", unk), "local2RateRaw": l2, "motorNo": p_int(mn, "motorNo", unk), "motorNoRaw": mn, "motor2Rate": p_flt(m2, "motor2Rate", unk), "motor2RateRaw": m2, "boatEquipmentNo": p_beq(bq, unk), "boatEquipmentNoRaw": bq, "boat2Rate": p_flt(b2, "boat2Rate", unk), "boat2RateRaw": b2, "currentSeriesResultsRaw": sr, "hayamiRaceNo": p_int(hy, "hayamiRaceNo", unk, True), "hayamiRaw": hy, "unknownFields": unk, "rawHex": line.hex()}

def parse_b_bytes(raw_bytes: bytes) -> dict[str, Any]:
    lines = raw_bytes.splitlines(); races, anomalies, venues = [], [], []
    vc = vn = rd = dn = cr = None
    def fin():
        nonlocal cr
        if cr is None: return
        rs = cr["racers"]; cr["racerCount"] = len(rs)
        sl = [r["boatNo"] for r in rs]
        dp = sorted({s for s in sl if sl.count(s) > 1})
        cr["duplicateBoatNos"] = dp; cr["sixRacerRows"] = len(rs) == 6 and not dp
        if len(rs) != 6: anomalies.append({"type": "RACER_COUNT_NOT_SIX", "raceId": cr["raceId"], "count": len(rs)})
        if dp: anomalies.append({"type": "DUPLICATE_BOAT_NO", "raceId": cr["raceId"], "boatNos": dp})
        races.append(cr); cr = None
    for i, line in enumerate(lines):
        ln = i + 1; mb = BBGN_RE.match(line)
        if mb:
            fin(); vc = mb.group(1).decode("ascii"); vn = rd = dn = None
            if vc not in venues: venues.append(vc)
            continue
        if BEND_RE.match(line): fin(); vc = None; continue
        if vc is not None and rd is None:
            mv = VENUE_RE.search(dec(line).translate(ZEN).strip())
            if mv:
                dn = int(mv.group(1))
                try: rd = datetime(int(mv.group(2)), int(mv.group(3)), int(mv.group(4))).date().isoformat()
                except ValueError: rd = None
                vn = re.sub(r"[\s\u3000]", "", mv.group(5)); continue
        if vc is not None:
            mr = RACE_RE.match(dec(line).translate(ZEN))
            if mr:
                fin(); rno = int(mr.group(1))
                rid = f"{rd.replace(chr(45), chr(42)*0)}_{vc}_{rno:02d}" if (rd and 1 <= rno <= 12) else None
                cr = {"raceId": rid, "raceDate": rd, "venue": vn, "venueCode": vc, "dayNo": dn, "raceNo": rno, "raceTitleRaw": mr.group(2).strip(), "isFixedEntry": "進入固定" in mr.group(2), "distanceMeters": int(mr.group(3)), "deadlineTime": mr.group(4), "headerLineNumber": ln, "headerRawHex": line.hex(), "racers": []}; continue
        if cr is not None:
            p = parse_b_racer_row(line, ln)
            if p is not None:
                if not p.get("valid"): anomalies.append({"type": "INVALID_RACER_ROW_LENGTH", "raceId": cr["raceId"], "lineNumber": ln, "byteLength": p["byteLength"], "rawHex": p["rawHex"]})
                else: del p["valid"]; cr["racers"].append(p)
    fin()
    return {"parserVersion": "1.0.0", "encoding": "CP932", "sourceLineCount": len(lines), "venueCount": len(venues), "venueCodes": venues, "raceCount": len(races), "anomalyCount": len(anomalies), "races": races, "anomalies": anomalies}

def parse_b_file(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    res = parse_b_bytes(Path(input_path).read_bytes())
    out = Path(output_path); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res