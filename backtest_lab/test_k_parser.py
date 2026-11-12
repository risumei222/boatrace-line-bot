import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from parse_k import (
    parse_racer_row,
    parse_venue_header,
    RACE_HEADER_RE,
)


def make_test_row() -> bytes:
    """
    固定幅構造の単体テスト用行。
    公式実データそのものではなく、項目位置の確認用。
    """
    row = bytearray(b" " * 66)

    row[2:4] = b"01"
    row[6:7] = b"1"
    row[8:12] = b"3876"

    # 16バイトのCP932選手名
    name = "中　辻　崇　人".encode("cp932")
    row[13:29] = name

    row[30:32] = b"21"
    row[34:37] = b"106"
    row[39:43] = b"6.80"
    row[46:47] = b"1"
    row[51:55] = b"0.08"
    row[60:66] = b"1.50.2"

    return bytes(row)


class TestKParser(unittest.TestCase):

    def test_parse_fixed_width_racer_row(self):
        parsed = parse_racer_row(make_test_row())

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["rank"], 1)
        self.assertEqual(parsed["boatNo"], 1)
        self.assertEqual(parsed["racerNo"], "3876")
        self.assertEqual(parsed["motorNoRaw"], "21")
        self.assertEqual(parsed["boatEquipmentNoRaw"], "106")
        self.assertEqual(parsed["exhibitionTime"], 6.80)
        self.assertEqual(parsed["entryCourse"], 1)
        self.assertEqual(parsed["st"], 0.08)
        self.assertEqual(parsed["raceTimeRaw"], "1.50.2")
        self.assertEqual(
            len(bytes.fromhex(parsed["rawHex"])), 66
        )

    def test_short_line_is_not_racer_row(self):
        self.assertIsNone(
            parse_racer_row(b"short")
        )

    def test_invalid_boat_number_is_not_racer_row(self):
        row = bytearray(make_test_row())
        row[6:7] = b"7"

        self.assertIsNone(
            parse_racer_row(bytes(row))
        )

    def test_non_numeric_rank_is_preserved(self):
        row = bytearray(make_test_row())
        row[2:4] = b"S0"

        parsed = parse_racer_row(bytes(row))

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["rankRaw"], "S0")
        self.assertIsNone(parsed["rank"])

    def test_venue_header_fukuoka(self):
        line = (
            "第 1日 2026/11/10 ボートレース福　岡"
            .encode("cp932")
        )

        parsed = parse_venue_header(line)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["raceDate"], "2026-11-10")
        self.assertEqual(parsed["venue"], "福岡")
        self.assertEqual(parsed["venueCode"], "22")
        self.assertTrue(parsed["valid"])

    def test_venue_header_ashiya(self):
        line = (
            "第 4日 2025/11/12 ボートレース芦　屋"
            .encode("cp932")
        )

        parsed = parse_venue_header(line)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["venue"], "芦屋")
        self.assertEqual(parsed["venueCode"], "21")

    def test_detail_race_header_is_detected(self):
        line = (
            "1R カタメン１予 H1800m 晴 風 東 4m 波 4cm"
            .encode("cp932")
        )

        self.assertIsNotNone(
            RACE_HEADER_RE.match(line)
        )

    def test_summary_race_line_is_not_detail_header(self):
        line = "1R 1-3-2 930円".encode("cp932")

        self.assertIsNone(
            RACE_HEADER_RE.match(line)
        )


if __name__ == "__main__":
    unittest.main()
