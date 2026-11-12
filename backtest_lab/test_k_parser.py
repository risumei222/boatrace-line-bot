import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent)
)

from backtest_lab.parse_k import (
    parse_k_bytes,
    parse_racer_row,
    RACE_HEADER_RE,
)


def make_racer_row(
    boat_no,
    racer_no,
    course,
    rank="01",
):
    row = bytearray(b" " * 66)

    row[2:4] = rank.encode("ascii")
    row[6:7] = str(boat_no).encode("ascii")
    row[8:12] = f"{racer_no:04d}".encode("ascii")

    # 16バイトの選手名欄
    row[13:29] = "テスト選手".encode("cp932").ljust(
        16, b"\x81\x40"
    )

    row[30:32] = b" 1"
    row[34:37] = b" 10"
    row[39:43] = b"6.80"

    if course is not None:
        row[46:47] = str(course).encode("ascii")

    row[51:55] = b"0.15"
    row[60:66] = b"1.50.2"

    return bytes(row)


def make_race_header(race_no, distance):
    return (
        f"{race_no}R テスト H{distance}m 晴 風 東 4m 波 4cm"
    ).encode("cp932")


class TestRaceHeader(unittest.TestCase):

    def test_h1800_detected(self):
        self.assertIsNotNone(
            RACE_HEADER_RE.match(
                make_race_header(1, 1800)
            )
        )

    def test_h1200_detected(self):
        self.assertIsNotNone(
            RACE_HEADER_RE.match(
                make_race_header(2, 1200)
            )
        )

    def test_race_number_detected(self):
        match = RACE_HEADER_RE.match(
            make_race_header(12, 1800)
        )
        self.assertEqual(int(match.group(1)), 12)


class TestRacerRow(unittest.TestCase):

    def test_normal_course(self):
        row = make_racer_row(1, 3876, 1)
        result = parse_racer_row(row)

        self.assertIsNotNone(result)
        self.assertEqual(result["boatNo"], 1)
        self.assertEqual(result["racerNo"], "3876")
        self.assertEqual(result["entryCourse"], 1)

    def test_blank_course_is_retained(self):
        row = make_racer_row(5, 3461, None)
        result = parse_racer_row(row)

        self.assertIsNotNone(result)
        self.assertEqual(result["boatNo"], 5)
        self.assertIsNone(result["entryCourse"])
        self.assertEqual(result["entryCourseRaw"], " ")

    def test_s0_rank_is_preserved(self):
        row = make_racer_row(1, 3876, 1, rank="S0")
        result = parse_racer_row(row)

        self.assertIsNotNone(result)
        self.assertEqual(result["rankRaw"], "S0")
        self.assertIsNone(result["rank"])

    def test_s2_rank_is_preserved(self):
        row = make_racer_row(2, 4010, 2, rank="S2")
        result = parse_racer_row(row)

        self.assertIsNotNone(result)
        self.assertEqual(result["rankRaw"], "S2")
        self.assertIsNone(result["rank"])


class TestRaceGrouping(unittest.TestCase):

    def test_h1200_starts_new_race(self):
        lines = [
            b"\x8f\xe6\x82P\x93\xfa",
            make_race_header(1, 1800),
        ]

        for boat in range(1, 7):
            lines.append(
                make_racer_row(
                    boat, 3800 + boat, boat
                )
            )

        lines.append(make_race_header(2, 1200))

        for boat in range(1, 7):
            lines.append(
                make_racer_row(
                    boat, 3900 + boat, boat
                )
            )

        result = parse_k_bytes(
            b"\r\n".join(lines)
        )

        self.assertEqual(result["raceCount"], 2)
        self.assertEqual(
            result["races"][0]["racerCount"], 6
        )
        self.assertEqual(
            result["races"][1]["racerCount"], 6
        )
        self.assertEqual(
            result["races"][1]["raceNo"], 2
        )

    def test_blank_course_does_not_reduce_racer_count(self):
        lines = [
            make_race_header(1, 1800)
        ]

        for boat in range(1, 7):
            course = None if boat == 5 else boat
            lines.append(
                make_racer_row(
                    boat, 3800 + boat, course
                )
            )

        result = parse_k_bytes(
            b"\r\n".join(lines)
        )

        race = result["races"][0]

        self.assertEqual(race["racerCount"], 6)
        self.assertEqual(
            race["unknownEntryCourseBoatNos"], [5]
        )
        self.assertEqual(
            race["sixRacerRows"], True
        )


if __name__ == "__main__":
    unittest.main()
