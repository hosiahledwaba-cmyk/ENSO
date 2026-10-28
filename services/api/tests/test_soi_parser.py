"""Regression tests for NOAA CPC Southern Oscillation Index (SOI) parser.

Verifies:
1. Extraction of only the intended STANDARDIZED DATA series (ignoring ANOMALY section).
2. Proper parsing of fixed-width columns with touching negative numbers (-3.3-999.9).
3. Skipping of missing-data sentinels (<= -99.0, e.g. -999.9).
4. Strict enforcement of at most one observation per source-month.
5. Graceful handling of malformed, incomplete, and non-numeric inputs.
6. Ingestion idempotency.
"""

from __future__ import annotations

from enso_api.ingestion.coordinator import NoaaSoiProvider

SAMPLE_MULTI_SECTION_SOI_TEXT = """\
(STAND TAHITI - STAND DARWIN)  SEA LEVEL PRESS
                        ANOMALY

YEAR   JAN   FEB   MAR   APR   MAY   JUN   JUL   AUG   SEP   OCT   NOV   DEC
1951   2.5   1.5  -0.2  -0.5  -1.1   0.3  -1.7  -0.4  -1.8  -1.6  -1.3  -1.2
1952  -1.5  -1.0   0.9  -0.4   1.2   1.2   0.8   0.1  -0.4   0.6   0.0  -2.0
(STAND TAHITI - STAND DARWIN)  SEA LEVEL PRESS
                    STANDARDIZED    DATA

YEAR   JAN   FEB   MAR   APR   MAY   JUN   JUL   AUG   SEP   OCT   NOV   DEC
1951   1.5   0.9  -0.1  -0.3  -0.7   0.2  -1.0  -0.2  -1.1  -1.0  -0.8  -0.7
1952  -0.9  -0.6   0.5  -0.2   0.8   0.7   0.5   0.1  -0.2   0.4   0.0  -1.2
2026   1.1   1.4   1.2  -0.6  -0.9  -1.4  -2.4  -1.1  -2.0-999.9-999.9-999.9
2027-999.9-999.9-999.9-999.9-999.9-999.9-999.9-999.9-999.9-999.9-999.9-999.9
"""


def test_soi_parser_extracts_only_standardized_series() -> None:
    """Verify that only values from STANDARDIZED DATA are extracted, ignoring ANOMALY table."""
    provider = NoaaSoiProvider()
    rows = provider.parse_soi_text(SAMPLE_MULTI_SECTION_SOI_TEXT)

    # 1951 and 1952 should have standardized values (1.5, 0.9, ...), NOT anomaly values (2.5, 1.5, ...)
    jan_1951 = next(r for r in rows if r["year"] == 1951 and r["month"] == 1)
    assert jan_1951["soi_standardized"] == 1.5  # Standardized value, not anomaly 2.5
    assert jan_1951["date"] == "1951-01-01"

    feb_1951 = next(r for r in rows if r["year"] == 1951 and r["month"] == 2)
    assert feb_1951["soi_standardized"] == 0.9  # Standardized value, not anomaly 1.5


def test_soi_parser_no_duplicate_months() -> None:
    """Verify that each year-month tuple appears at most once in parsed records."""
    provider = NoaaSoiProvider()
    rows = provider.parse_soi_text(SAMPLE_MULTI_SECTION_SOI_TEXT)

    dates = [r["date"] for r in rows]
    assert len(dates) == len(set(dates)), "Duplicate dates found in parsed SOI records"


def test_soi_parser_handles_touching_negative_numbers() -> None:
    """Verify that abutting fixed-width negative numbers (-2.0-999.9) are parsed correctly."""
    provider = NoaaSoiProvider()
    rows = provider.parse_soi_text(SAMPLE_MULTI_SECTION_SOI_TEXT)

    # In 2026, September is -2.0, followed by -999.9 for Oct, Nov, Dec
    sep_2026 = next((r for r in rows if r["year"] == 2026 and r["month"] == 9), None)
    assert sep_2026 is not None, "September 2026 was lost due to touching sentinel tokens"
    assert sep_2026["soi_standardized"] == -2.0

    # October, November, December 2026 are sentinels (-999.9) and must be omitted
    oct_2026 = next((r for r in rows if r["year"] == 2026 and r["month"] == 10), None)
    assert oct_2026 is None, "Sentinel value -999.9 was not skipped"


def test_soi_parser_skips_all_sentinel_years() -> None:
    """Verify that years with all -999.9 missing values produce zero records."""
    provider = NoaaSoiProvider()
    rows = provider.parse_soi_text(SAMPLE_MULTI_SECTION_SOI_TEXT)

    # 2027 is all sentinels, should have zero records
    records_2027 = [r for r in rows if r["year"] == 2027]
    assert len(records_2027) == 0


def test_soi_parser_handles_malformed_input() -> None:
    """Verify parser resilience against corrupt lines, letters, and incomplete rows."""
    malformed_text = """\
STANDARDIZED DATA
YEAR JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC
1980  1.0  abc  0.5 -999.9 -999.9 -999.9 -999.9 -999.9 -999.9 -999.9 -999.9 -999.9
1981  corrupted line with random words
1982  0.5  0.2
NOTAYEAR 1.0 2.0
"""
    provider = NoaaSoiProvider()
    rows = provider.parse_soi_text(malformed_text)

    # 1980 has month 1 (1.0) and month 3 (0.5); month 2 is 'abc' so skipped
    assert len(rows) == 2
    assert rows[0]["month"] == 1 and rows[0]["soi_standardized"] == 1.0
    assert rows[1]["month"] == 3 and rows[1]["soi_standardized"] == 0.5


def test_soi_parser_idempotency() -> None:
    """Verify that multiple parsing passes on the same text yield identical results."""
    provider = NoaaSoiProvider()
    rows1 = provider.parse_soi_text(SAMPLE_MULTI_SECTION_SOI_TEXT)
    rows2 = provider.parse_soi_text(SAMPLE_MULTI_SECTION_SOI_TEXT)
    assert rows1 == rows2
