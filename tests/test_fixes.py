import json
from datetime import date, datetime

from helenservice.cli import _json_serializer


def test_json_serializer_date():
    d = date(2024, 5, 8)
    assert _json_serializer(d) == "2024-05-08"
    assert json.dumps({"date": d}, default=_json_serializer) == '{"date": "2024-05-08"}'


def test_json_serializer_datetime():
    dt = datetime(2024, 5, 8, 12, 34, 56)
    assert _json_serializer(dt) == "20240508123456"


def test_json_serializer_object():
    class TestObj:
        def __init__(self):
            self.foo = "bar"

    assert _json_serializer(TestObj()) == {"foo": "bar"}
