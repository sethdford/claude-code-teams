"""Tests for csvparse.parse_csv_line — DETERMINISTIC failure modes."""
from csvparse import parse_csv_line


def test_simple_split():
    assert parse_csv_line("a,b,c") == ["a", "b", "c"]


def test_quoted_field_with_comma():
    """The classic CSV gotcha: a comma INSIDE a quoted field should not split."""
    assert parse_csv_line('"hello, world",b,c') == ["hello, world", "b", "c"]


def test_escaped_double_quote():
    """A doubled double-quote inside a quoted field becomes a literal double-quote."""
    assert parse_csv_line('"he said ""hi""",b') == ['he said "hi"', "b"]


def test_strips_trailing_newline():
    assert parse_csv_line("a,b\n") == ["a", "b"]


def test_strips_trailing_crlf():
    assert parse_csv_line("a,b\r\n") == ["a", "b"]


def test_empty_fields_preserved():
    assert parse_csv_line(",a,,") == ["", "a", "", ""]


def test_quoted_at_end():
    assert parse_csv_line('a,"b,c"') == ["a", "b,c"]


def test_no_quotes_no_special():
    assert parse_csv_line("foo,bar,baz") == ["foo", "bar", "baz"]
