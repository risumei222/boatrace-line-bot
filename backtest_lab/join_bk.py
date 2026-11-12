def join_b_and_k(b_data: dict, k_data: dict) -> dict:
    b_races = {r["raceId"]: r for r in b_data.get("races", []) if "raceId" in r}
    k_results = {r["raceId"]: r for r in k_data.get("results", []) if "raceId" in r}
    all_ids = sorted(set(b_races.keys()) | set(k_results.keys()))
    joined, missing_b, missing_k = [], [], []
    for rid in all_ids:
        b_race, k_res = b_races.get(rid), k_results.get(rid)
        if b_race is None:
            missing_b.append(rid)
            continue
        if k_res is None:
            missing_k.append(rid)
            continue
        merged = dict(b_race)
        merged["result"] = k_res
        merged["resultStatus"] = k_res.get("resultStatus")
        merged["sanrentan"] = k_res.get("sanrentan")
        joined.append(merged)
    return {
        "joinVersion": "1.0.0",
        "bRaceCount": len(b_races),
        "kResultCount": len(k_results),
        "joinedCount": len(joined),
        "missingBCount": len(missing_b),
        "missingKCount": len(missing_k),
        "missingBIds": missing_b,
        "missingKIds": missing_k,
        "races": joined,
    }
