import copy, json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

BACKTEST_RUNNER_VERSION = "1.1.0"
DEFAULT_UNIT_STAKE_YEN = 100
PredictionEngineFn = Callable[[Dict[str, Any]], Dict[str, Any]]

@dataclass(frozen=True)
class EngineSpec:
    engine_id: str
    name: str
    status: str
    predict_fn: PredictionEngineFn

class BacktestIntegrityError(RuntimeError):
    pass

def unimplemented_stub_engine(prediction_input: Dict[str, Any]) -> Dict[str, Any]:
    if "evaluation" in prediction_input:
        raise BacktestIntegrityError("evaluation leaked into prediction_input")
    return {"action": "SKIP", "reason": "ENGINE_LOGIC_UNIMPLEMENTED", "bets": []}

def get_default_stub_engines() -> List[EngineSpec]:
    return [
        EngineSpec(eid, f"Engine_{eid} (Unimplemented)", "UNIMPLEMENTED_STUB", unimplemented_stub_engine)
        for eid in ("A", "B", "C", "D")
    ]

def _normalize_sanrentan_payouts(sanrentan: Any) -> Dict[str, int]:
    """
    Normalize sanrentan into {combination: payout}.
    Official parse_k_results.py output is a single dict; list is also supported safely.
    Never imputes None, malformed combinations, or invalid/negative payouts.
    """
    if sanrentan is None:
        return {}
    if isinstance(sanrentan, dict):
        items = [sanrentan]
    elif isinstance(sanrentan, list):
        items = sanrentan
    else:
        return {}
    pmap: Dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            return {}
        comb = item.get("combination")
        pay = item.get("payout")
        if not isinstance(comb, str) or not comb:
            return {}
        parts = comb.split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            return {}
        if isinstance(pay, bool) or not isinstance(pay, int) or pay < 0:
            return {}
        pmap[comb] = pay
    return pmap

def _is_normally_evaluable(ev: Dict[str, Any]) -> bool:
    if not isinstance(ev, dict) or ev.get("resultStatus") != "NORMAL":
        return False
    if ev.get("hasAbnormal") is not False:
        return False
    if ev.get("refundBoatNos") or ev.get("k0BoatNos") or ev.get("abnormalEntries"):
        return False
    return len(_normalize_sanrentan_payouts(ev.get("sanrentan"))) > 0

def _validate_comb(comb: str) -> None:
    if not isinstance(comb, str):
        raise BacktestIntegrityError(f"Invalid combination type: {type(comb).__name__}")
    p = comb.split("-")
    if len(p) != 3 or not all(x.isdigit() for x in p):
        raise BacktestIntegrityError(f"Invalid combination: {comb}")

def evaluate_single_engine(dataset: Dict[str, Any], engine: EngineSpec, *, unit_stake_yen: int = DEFAULT_UNIT_STAKE_YEN) -> Dict[str, Any]:
    if unit_stake_yen <= 0:
        raise ValueError("unit_stake_yen must be positive")
    records = dataset.get("records")
    if not isinstance(records, list):
        raise BacktestIntegrityError("Dataset missing records")
    tot = len(records)
    eval_cnt = non_eval = skip_cnt = bet_races = bet_cnt = hit_cnt = hit_races = stake_sum = pay_sum = excl_bets = 0
    logs: List[Dict[str, Any]] = []
    for rec in records:
        rid = rec.get("raceId")
        pin, ev = rec.get("prediction_input"), rec.get("evaluation")
        if not isinstance(pin, dict) or not isinstance(ev, dict):
            raise BacktestIntegrityError(f"Invalid record: {rid}")
        dec = engine.predict_fn(copy.deepcopy(pin))
        if not isinstance(dec, dict) or not isinstance(dec.get("bets", []), list):
            raise BacktestIntegrityError(f"Invalid decision on {rid}")
        bets = dec.get("bets") or []
        ok = _is_normally_evaluable(ev)
        eval_cnt += int(ok)
        non_eval += int(not ok)
        if not bets:
            skip_cnt += 1
            logs.append({"raceId": rid, "evaluable": ok, "action": "SKIP", "betCount": 0, "hitCount": 0, "stake": 0, "payout": 0})
            continue
        if not ok:
            excl_bets += len(bets)
            logs.append({"raceId": rid, "evaluable": False, "action": "EXCLUDED_ABNORMAL_OR_REFUND", "betCount": len(bets), "hitCount": 0, "stake": 0, "payout": 0})
            continue
        bet_races += 1
        pmap = _normalize_sanrentan_payouts(ev.get("sanrentan"))
        r_stake = r_pay = r_hits = 0
        for b in bets:
            if not isinstance(b, dict) or "combination" not in b:
                raise BacktestIntegrityError(f"Invalid bet on {rid}")
            _validate_comb(b["combination"])
            st = b.get("stake", unit_stake_yen)
            if isinstance(st, bool) or not isinstance(st, int) or st <= 0:
                raise BacktestIntegrityError(f"Invalid stake on {rid}")
            bet_cnt += 1
            r_stake += st
            if b["combination"] in pmap:
                r_pay += (pmap[b["combination"]] * st) // 100
                r_hits += 1
                hit_cnt += 1
        hit_races += int(r_hits > 0)
        stake_sum += r_stake
        pay_sum += r_pay
        logs.append({"raceId": rid, "evaluable": True, "action": "BET", "betCount": len(bets), "hitCount": r_hits, "stake": r_stake, "payout": r_pay})
    return {
        "engineId": engine.engine_id, "engineName": engine.name, "engineStatus": engine.status,
        "metrics": {
            "totalRaces": tot, "evaluableRaces": eval_cnt, "nonEvaluableRaces": non_eval,
            "skippedRaces": skip_cnt, "betRaces": bet_races, "betCount": bet_cnt,
            "excludedAbnormalBetCount": excl_bets, "hitCount": hit_cnt, "hitRaces": hit_races,
            "hitRatePerBet": round(hit_cnt / bet_cnt, 6) if bet_cnt else None,
            "hitRatePerBetRace": round(hit_races / bet_races, 6) if bet_races else None,
            "investmentAmount": stake_sum, "payoutAmount": pay_sum,
            "recoveryRate": round(pay_sum / stake_sum, 6) if stake_sum else None,
            "profit": pay_sum - stake_sum,
        },
        "raceLogs": logs,
    }

def run_backtest(dataset: Dict[str, Any], engines: Optional[Sequence[EngineSpec]] = None, *, unit_stake_yen: int = DEFAULT_UNIT_STAKE_YEN, include_race_logs: bool = False) -> Dict[str, Any]:
    engs = list(engines) if engines is not None else get_default_stub_engines()
    if len({e.engine_id for e in engs}) != len(engs):
        raise ValueError("Duplicate engine_id")
    res_map, comp = {}, []
    for e in engs:
        r = evaluate_single_engine(dataset, e, unit_stake_yen=unit_stake_yen)
        res_map[e.engine_id] = r if include_race_logs else {k: v for k, v in r.items() if k != "raceLogs"}
        comp.append({"engineId": e.engine_id, "engineName": e.name, "engineStatus": e.status, **r["metrics"]})
    return {
        "backtestRunnerVersion": BACKTEST_RUNNER_VERSION,
        "datasetBuilderVersion": dataset.get("datasetBuilderVersion"),
        "unitStakeYen": unit_stake_yen, "engineCount": len(engs),
        "engineComparison": comp, "engines": res_map,
    }

def format_backtest_summary(report: Dict[str, Any]) -> str:
    return json.dumps({k: report[k] for k in ("backtestRunnerVersion", "datasetBuilderVersion", "unitStakeYen", "engineComparison")}, ensure_ascii=False, indent=2)
