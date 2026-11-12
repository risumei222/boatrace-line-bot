from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


VENUE_CODES = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
    "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
    "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24",
}

VENUE_HEADER_RE = re.compile(
    r"^\s*第\s*\d+日\s+(\d{4}/\d{2}/\d{2})\s+ボートレース(.+?)\s*$"
)

# H1800m・H1200mなど、距離を限定せず認識する
RACE_HEADER_RE = re.compile(
    rb"^\s*(\d{1,2})R\b.*H\d+m(?:\s|$)",
    re.IGNORECASE,
)

ASCII_DIGITS_RE = re.compile(rb"^\d+$")
DECIMAL_RE = re.compile(r"^\d+\.\d+$")


def decode_cp932(value: bytes) -> str:
    return value.decode("cp932", errors="replace")


def normalize_venue_name(value: str) -> str:
    return re.sub(r"[\s\u3000]", "", value)


def parse_decimal(raw: str) -> float | None:
    value = raw.strip()

    if not DECIMAL_RE.fullmatch(value):
        return None

    try:
        return float(value)
    except ValueError:
        return None


def parse_venue_header(line: bytes) -> dict[str, Any] | None:
    text = decode_cp932(line).strip()
    match = VENUE_HEADER_RE.match(text)

    if not match:
        return None

    date_text = match.group(1)
    venue_name = normalize_venue_name(match.group(2))

    try:
        race_date = datetime.strptime(
            date_text, "%Y/%m/%d"
        ).date().isoformat()
    except ValueError:
        race_date = None

    venue_code = VENUE_CODES.get(venue_name)

    return {
        "raceDate": race_date,
        "venue": venue_name,
        "venueCode": venue_code,
        "dateRaw": date_text,
        "valid": race_date is not None and venue_code is not None,
    }


def parse_racer_row(
    line: bytes,
    line_number: int | None = None,
) -> dict[str, Any] | None:

    if len(line) < 66:
        return None

    rank_raw = line[2:4].strip()
    boat_raw = line[6:7]
    racer_no_raw = line[8:12]
    course_raw = line[46:47]

    if not rank_raw:
        return None

    if boat_raw not in (b"1", b"2", b"3", b"4", b"5", b"6"):
        return None

    if not ASCII_DIGITS_RE.fullmatch(racer_no_raw):
        return None

    # 進入コースが空欄でも選手行として保持する
    course_value = course_raw.strip()

    if course_value in (b"1", b"2", b"3", b"4", b"5", b"6"):
        entry_course = int(course_value)
    elif course_value == b"":
        entry_course = None
    else:
        return None

    name = decode_cp932(line[13:29])
    name = name.replace("\u3000", " ").strip()

    motor_raw = line[30:32].decode(
        "ascii", errors="replace"
    ).strip()

    equipment_raw = line[34:37].decode(
        "ascii", errors="replace"
    ).strip()

    exhibition_raw = line[39:43].decode(
        "ascii", errors="replace"
    ).strip()

    st_raw = line[51:55].decode(
        "ascii", errors="replace"
    ).strip()

    race_time_raw = line[60:66].decode(
        "ascii", errors="replace"
    ).strip()

    rank_text = rank_raw.decode(
        "ascii", errors="replace"
    )

    return {
        "lineNumber": line_number,
        "rankRaw": rank_text,
        "rank": int(rank_text) if rank_text.isdigit() else None,
        "boatNo": int(boat_raw),
        "racerNo": racer_no_raw.decode("ascii"),
        "racerName": name,
        "motorNoRaw": motor_raw,
        "boatEquipmentNoRaw": equipment_raw,
        "exhibitionTimeRaw": exhibition_raw,
        "exhibitionTime": parse_decimal(exhibition_raw),
        "entryCourse": entry_course,
        "entryCourseRaw": decode_cp932(course_raw),
        "stRaw": st_raw,
        "st": parse_decimal(st_raw),
        "raceTimeRaw": race_time_raw,
        "rawHex": line.hex(),
    }


def parse_k_bytes(raw_bytes: bytes) -> dict[str, Any]:
    lines = raw_bytes.splitlines()

    races = []
    anomalies = []

    current_venue = None
    current_race = None

    def finish_race():
        nonlocal current_race

        if current_race is None:
            return

        current_race["racerCount"] = len(
            current_race["racers"]
        )

        slots = [
            racer["boatNo"]
            for racer in current_race["racers"]
        ]

        current_race["duplicateBoatNos"] = sorted({
            slot for slot in slots if slots.count(slot) > 1
        })

        current_race["sixRacerRows"] = (
            len(current_race["racers"]) == 6
        )

        unknown_courses = [
            racer["boatNo"]
            for racer in current_race["racers"]
            if racer["entryCourse"] is None
        ]

        current_race["unknownEntryCourseBoatNos"] = (
            unknown_courses
        )

        if current_race["racerCount"] != 6:
            anomalies.append({
                "type": "RACER_COUNT_NOT_SIX",
                "raceId": current_race["raceId"],
                "count": current_race["racerCount"],
            })

        if current_race["duplicateBoatNos"]:
            anomalies.append({
                "type": "DUPLICATE_BOAT_NO",
                "raceId": current_race["raceId"],
                "boatNos": current_race["duplicateBoatNos"],
            })

        if unknown_courses:
            anomalies.append({
                "type": "UNKNOWN_ENTRY_COURSE",
                "raceId": current_race["raceId"],
                "boatNos": unknown_courses,
            })

        races.append(current_race)
        current_race = None

    for index, line in enumerate(lines):
        line_number = index + 1

        venue = parse_venue_header(line)

        if venue is not None:
            finish_race()
            current_venue = venue

            if not venue["valid"]:
                anomalies.append({
                    "type": "UNKNOWN_OR_INVALID_VENUE",
                    "lineNumber": line_number,
                    "venue": venue["venue"],
                    "dateRaw": venue["dateRaw"],
                })

            continue

        race_match = RACE_HEADER_RE.match(line)

        if race_match:
            finish_race()

            race_no = int(race_match.group(1))

            date_value = (
                current_venue["raceDate"]
                if current_venue else None
            )

            venue_code = (
                current_venue["venueCode"]
                if current_venue else None
            )

            venue_name = (
                current_venue["venue"]
                if current_venue else None
            )

            race_id = None

            if date_value and venue_code and 1 <= race_no <= 12:
                race_id = (
                    f"{date_value.replace('-', '')}_"
                    f"{venue_code}_{race_no:02d}"
                )

            current_race = {
                "raceId": race_id,
                "raceDate": date_value,
                "venue": venue_name,
                "venueCode": venue_code,
                "raceNo": race_no,
                "headerLineNumber": line_number,
                "headerRaw": decode_cp932(line).strip(),
                "racers": [],
                "otherLines": [],
            }

            if current_venue is None:
                anomalies.append({
                    "type": "RACE_WITHOUT_VENUE_CONTEXT",
                    "lineNumber": line_number,
                    "raceNo": race_no,
                })

            continue

        if current_race is not None:
            racer = parse_racer_row(line, line_number)

            if racer is not None:
                current_race["racers"].append(racer)

            elif line.strip():
                current_race["otherLines"].append({
                    "lineNumber": line_number,
                    "rawText": decode_cp932(line),
                    "rawHex": line.hex(),
                })

    finish_race()

    return {
        "parserVersion": "1.1.0",
        "encoding": "CP932",
        "sourceLineCount": len(lines),
        "raceCount": len(races),
        "anomalyCount": len(anomalies),
        "races": races,
        "anomalies": anomalies,
    }


def parse_k_file(
    input_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:

    input_path = Path(input_path)
    output_path = Path(output_path)

    result = parse_k_bytes(input_path.read_bytes())

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return result
