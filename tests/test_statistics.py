import pytest

from app.statistics import number, parse_csv


def test_parse_danish_labels_and_missing_values():
    csv_text = (
        'BRANCHE07;TAL;TID;INDHOLD\n'
        '620100;Arbejdssteder ultimo november;2024;1.234,5\n'
        '620100;Job ultimo november;2024;..\n'
        '620100;Fuldtidsbesk\u00e6ftigede;2024;250\n'
        '620100;\u00c5rlig l\u00f8nsum (Mio. kr.);2024;56,25\n'
    )
    assert parse_csv(csv_text, "620100", 2024) == {
        "workplaces": 1234.5, "jobs": None,
        "full_time_employment": 250, "payroll_million_dkk": 56.25,
    }


def test_reject_incomplete_statbank_csv():
    with pytest.raises(ValueError, match="missing requested"):
        parse_csv("BRANCHE07;TAL;TID;INDHOLD\n620100;ARBSTED;2024;1\n", "620100", 2024)


@pytest.mark.parametrize("text, expected", [
    ("1234", 1234), ("1.234", 1234), ("12.345.678", 12345678),
    ("1.234,5", 1234.5), ("12,5", 12.5), ("1 234", 1234),
    ("1\u00a0234", 1234), ("0", 0), ("9007199254740993", 9007199254740993),
    ("9007199254740993,0", 9007199254740993),
    ("..", None), ("", None), (":", None), ("-", None), ("...", None),
])
def test_number_parsing(text, expected):
    assert number(text) == expected


@pytest.mark.parametrize("text", ["NaN", "inf", "1e3", "12.5", "1.23.456", "1,2,3", "1 2", "1.234 567"])
def test_invalid_number_is_rejected(text):
    with pytest.raises(ValueError):
        number(text)


@pytest.mark.parametrize("text", [
    "TAL;INDHOLD\nARBSTED;1\n",
    "BRANCHE07;TAL;TID;TID\n620100;ARBSTED;2024;1\n",
    "BRANCHE07;TAL;TID;INDHOLD\n620100;ARBSTED;2024\n",
    "BRANCHE07;TAL;TID;INDHOLD\n620100;ARBSTED;2024;1;extra\n",
    'BRANCHE07;TAL;TID;INDHOLD\n620100;ARBSTED;2024;"1\n',
    "BRANCHE07;TAL;TID;INDHOLD\n620100;Unknown;2024;1\n",
    "BRANCHE07;TAL;TID;INDHOLD\n620100;ARBSTED;2024;1\n620100;ARBSTED;2024;1\n",
    "BRANCHE07;TAL;TID;INDHOLD\n212000;ARBSTED;2024;1\n",
    "BRANCHE07;TAL;TID;INDHOLD\n620100;ARBSTED;2023;1\n",
])
def test_malformed_or_mismatched_csv_is_rejected(text):
    with pytest.raises(ValueError):
        parse_csv(text, "620100", 2024)


@pytest.mark.parametrize("value, expected", [("..", None), ("0", 0)])
def test_all_missing_or_zero_statistics(value, expected):
    text = "BRANCHE07;TAL;TID;INDHOLD\n" + "".join(
        f"212000;{metric};2024;{value}\n"
        for metric in ("ARBSTED", "ANSATTE", "FULDBESK", "L\u00d8NSUM")
    )
    assert set(parse_csv(text, "212000", 2024).values()) == {expected}
