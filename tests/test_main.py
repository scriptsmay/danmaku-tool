"""FastAPI entrypoint helper tests."""
from __future__ import annotations

from danmaku_tool.main import _coerce_json_rows


def test_coerce_json_rows_accepts_single_object():
    rows = _coerce_json_rows('{"LocalAddress":"127.0.0.1","OwningProcess":1234}')

    assert rows == [{"LocalAddress": "127.0.0.1", "OwningProcess": 1234}]


def test_coerce_json_rows_accepts_array_and_filters_non_objects():
    rows = _coerce_json_rows('[{"OwningProcess":1234},"skip",{"OwningProcess":5678}]')

    assert rows == [{"OwningProcess": 1234}, {"OwningProcess": 5678}]
