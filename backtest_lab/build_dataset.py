import copy
from typing import Any, Dict, List, Optional
from backtest_lab.join_bk import join_b_and_k

DATASET_BUILDER_VERSION = "1.0.0"

FORBIDDEN_PREDICTION_KEYS = frozenset({
    "result",
    "results",
    "resultStatus",
    "hasAbnormal",
    "finishingOrder",
    "racerOutcomes",
    "abnormalEntries",
    "refundBoatNos",
    "k0BoatNos",
    "sanrentan",
    "payout",
    "popularity",
    "actualCourse",
    "actualSt",
    "st",
    "rank",
    "finishRank",
})

EVALUATION_KEYS = (
    "resultStatus",
    "hasAbnormal",
    "finishingOrder",
    "racerOutcomes",
    "abnormalEntries",
    "refundBoatNos",
    "k0BoatNos",
    "sanrentan",
    "unknownItems",
)


class DatasetBuildError(ValueError):
    """Raised when B/K join integrity fails or required identifiers are missing."""


class DataLeakError(RuntimeError):
    """Raised when post-race or same-day/future K data threatens to enter prediction_input."""


def _assert_no_forbidden_keys(obj: Any, path: str = "prediction_input") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_PREDICTION_KEYS:
                raise DataLeakError(f"Forbidden key '{k}' detected at {path}.{k}")
            _assert_no_forbidden_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _assert_no_forbidden_keys(item, f"{path}[{idx}]")


def validate_historical_k_sources(target_race_date: str, historical_k_list: Optional[List[Dict[str, Any]]]) -> List[str]:
    """Ensure any historical K dataset referenced is strictly earlier than target_race_date."""
    if not historical_k_list:
        return []
    accepted_dates: List[str] = []
    for k_doc in historical_k_list:
        for res in k_doc.get("results", []):
            r_date = res.get("raceDate")
            if not r_date or r_date >= target_race_date:
                raise DataLeakError(
                    f"Data leak blocked: K result date '{r_date}' is not strictly before target date '{target_race_date}'"
                )
            if r_date not in accepted_dates:
                accepted_dates.append(r_date)
    return sorted(accepted_dates)


def build_backtest_dataset(
    b_data: Dict[str, Any],
    k_data: Dict[str, Any],
    *,
    strict_join: bool = True,
    historical_k_list: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Build a leak-free dataset separating pre-race `prediction_input` (from B only)
    and post-race `evaluation` (from K only), without mutating or imputing raw values.
    """
    b_copy = copy.deepcopy(b_data)
    k_copy = copy.deepcopy(k_data)

    joined_out = join_b_and_k(b_copy, k_copy)

    if strict_join and (joined_out["missingBCount"] > 0 or joined_out["missingKCount"] > 0):
        raise DatasetBuildError(
            f"B/K raceId mismatch: missingB={joined_out['missingBIds']}, missingK={joined_out['missingKIds']}"
        )

    records: List[Dict[str, Any]] = []

    for merged_race in joined_out["races"]:
        race_id = merged_race.get("raceId")
        race_date = merged_race.get("raceDate")
        if not race_id or not race_date:
            raise DatasetBuildError("Missing raceId or raceDate in joined race record")

        prior_dates = validate_historical_k_sources(race_date, historical_k_list)

        k_res = merged_race.get("result")
        if not isinstance(k_res, dict):
            raise DatasetBuildError(f"Missing K result object for raceId={race_id}")

        # Build prediction_input strictly from B-derived fields (excluding merged K fields)
        b_only_fields = {
            k: copy.deepcopy(v)
            for k, v in merged_race.items()
            if k not in ("result", "resultStatus", "sanrentan")
        }

        prediction_input: Dict[str, Any] = {
            **b_only_fields,
            "unverifiedPreRace": {
                "exhibition": "UNKNOWN",
                "weather": "UNKNOWN",
            },
            "historicalFeatures": {
                "status": "UNCOMPUTED_DESIGN_PLACEHOLDER",
                "allowedKDateRule": f"raceDate < {race_date}",
                "validatedPriorKDates": prior_dates,
            },
        }

        # Guard against any accidental leak into prediction_input
        _assert_no_forbidden_keys(prediction_input)

        # Build evaluation strictly from K-derived fields
        evaluation: Dict[str, Any] = {
            key: copy.deepcopy(k_res.get(key)) for key in EVALUATION_KEYS
        }

        lineage: Dict[str, Any] = {
            "datasetBuilderVersion": DATASET_BUILDER_VERSION,
            "bParserVersion": b_copy.get("parserVersion"),
            "kResultParserVersion": k_copy.get("resultParserVersion"),
            "kSourceParserVersion": k_copy.get("sourceParserVersion"),
            "joinVersion": joined_out.get("joinVersion"),
            "bEncoding": b_copy.get("encoding"),
            "kEncoding": k_copy.get("encoding"),
            "bHeaderLineNumber": merged_race.get("headerLineNumber"),
            "bHeaderRawHex": merged_race.get("headerRawHex"),
        }

        records.append({
            "raceId": race_id,
            "prediction_input": prediction_input,
            "evaluation": evaluation,
            "lineage": lineage,
        })

    return {
        "datasetBuilderVersion": DATASET_BUILDER_VERSION,
        "recordCount": len(records),
        "bRaceCount": joined_out["bRaceCount"],
        "kResultCount": joined_out["kResultCount"],
        "missingBCount": joined_out["missingBCount"],
        "missingKCount": joined_out["missingKCount"],
        "records": records,
    }
