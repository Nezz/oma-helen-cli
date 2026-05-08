import json
from datetime import date, datetime
from unittest.mock import MagicMock
import pytest
from helenservice.cli import _json_serializer
from helenservice.helen_session import HelenSession
from helenservice.api_exceptions import HelenAuthenticationException

def test_json_serializer_date():
    d = date(2024, 5, 8)
    serialized = _json_serializer(d)
    assert serialized == "2024-05-08"
    
    # Test through json.dumps
    res = json.dumps({"date": d}, default=_json_serializer)
    assert res == '{"date": "2024-05-08"}'

def test_json_serializer_datetime():
    dt = datetime(2024, 5, 8, 12, 34, 56)
    serialized = _json_serializer(dt)
    assert serialized == "20240508123456"

def test_json_serializer_object():
    class TestObj:
        def __init__(self):
            self.foo = "bar"
    
    obj = TestObj()
    serialized = _json_serializer(obj)
    assert serialized == {"foo": "bar"}

def test_follow_redirects_max_depth():
    session = HelenSession()
    session._session = MagicMock()
    
    # Mock a response that always has a location header
    mock_response = MagicMock()
    mock_response.headers = {"Location": "http://example.com/redirect"}
    
    # Mock session.get to return the same response
    session._session.get.return_value = mock_response
    
    with pytest.raises(HelenAuthenticationException, match="Max redirects"):
        session._follow_redirects(mock_response)

def test_follow_redirects_none_session():
    session = HelenSession()
    session._session = None # Ensure it is None
    
    mock_response = MagicMock()
    mock_response.headers = {"Location": "http://example.com/redirect"}
    
    with pytest.raises(HelenAuthenticationException, match="Session is None"):
        session._follow_redirects(mock_response)

def test_follow_redirects_success():
    session = HelenSession()
    session._session = MagicMock()
    
    # 1. Initial response with Location
    # 2. Second response without Location
    
    resp1 = MagicMock()
    resp1.headers = {"Location": "http://example.com/2"}
    
    resp2 = MagicMock()
    resp2.headers = {} # No location
    
    session._session.get.return_value = resp2
    
    final_resp = session._follow_redirects(resp1)
    
    assert final_resp == resp2
    session._session.get.assert_called_once_with("http://example.com/2", timeout=pytest.approx(30))
