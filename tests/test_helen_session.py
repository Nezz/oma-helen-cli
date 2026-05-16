import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from helenservice.api_exceptions import HelenAuthenticationException
from helenservice.const import HELEN_AUTH_ENDPOINT, HELEN_AUTH_PARAMS, HELEN_SESSION_RENEWAL_URL, HTTP_READ_TIMEOUT
from helenservice.helen_session import HelenSession


def _html_form(action: str, code: str = "abc", state: str = "xyz") -> str:
    return (
        f'<form action="{action}">'
        f'<input name="code" value="{code}"/>'
        f'<input name="state" value="{state}"/>'
        f'<button>Continue</button></form>'
    )


def _html_link(href: str) -> str:
    return f'<html><body><a href="{href}">Continue</a></body></html>'


def _mock_response(text: str, status: int = 200, url: str = "https://example.com") -> MagicMock:
    r = MagicMock()
    r.text = text
    r.status_code = status
    r.url = url
    return r


def _build_session(*, inject_access_token: bool = True) -> HelenSession:
    """HelenSession with mocked requests.Session wired through the full 5-step flow."""
    session = HelenSession()
    mock_requests = MagicMock()
    session._session = mock_requests

    mock_requests.post.side_effect = [
        _mock_response(_html_form("/uas/login-form"), url="https://login.helen.fi/uas/auth"),   # step 1
        _mock_response(_html_form("https://www.helen.fi/continue"), url="https://login.helen.fi/uas/login-form"),  # step 2
    ]
    mock_requests.get.side_effect = [
        _mock_response(_html_link("https://oma.helen.fi/v21/callback"), url="https://www.helen.fi/continue"),       # step 3
        _mock_response(_html_form("https://www.helen.fi/authResponse"), url="https://oma.helen.fi/v21/callback"),   # step 4
        _mock_response("<html>done</html>", url="https://www.helen.fi/authResponse"),                               # step 5
    ]
    mock_requests.cookies.get.return_value = "test-access-token" if inject_access_token else None
    return session


class TestDoFullLogin:
    def test_step1_posts_to_auth_endpoint_with_correct_params(self):
        session = _build_session()
        session._do_full_login("user@example.com", "secret")

        first_post = session._session.post.call_args_list[0]
        assert first_post.args[0] == HELEN_AUTH_ENDPOINT
        assert first_post.kwargs["params"] == HELEN_AUTH_PARAMS
        assert first_post.kwargs["timeout"] == HTTP_READ_TIMEOUT

    def test_step2_posts_credentials_to_scraped_login_form_url(self):
        session = _build_session()
        session._do_full_login("user@example.com", "secret")

        second_post = session._session.post.call_args_list[1]
        assert second_post.args[0] == "https://login.helen.fi/uas/login-form"
        assert second_post.kwargs["data"] == {"username": "user@example.com", "password": "secret"}

    def test_step3_submits_continue_form_with_code_and_state(self):
        session = _build_session()
        session._do_full_login("user@example.com", "secret")

        first_get = session._session.get.call_args_list[0]
        assert first_get.args[0] == "https://www.helen.fi/continue"
        assert first_get.kwargs["params"] == {"code": "abc", "state": "xyz"}

    def test_step4_follows_link_from_proceed_page(self):
        session = _build_session()
        session._do_full_login("user@example.com", "secret")

        second_get = session._session.get.call_args_list[1]
        assert second_get.args[0] == "https://oma.helen.fi/v21/callback"

    def test_step5_submits_second_code_exchange(self):
        session = _build_session()
        session._do_full_login("user@example.com", "secret")

        third_get = session._session.get.call_args_list[2]
        assert third_get.args[0] == "https://www.helen.fi/authResponse"
        assert third_get.kwargs["params"] == {"code": "abc", "state": "xyz"}

    def test_raises_if_no_access_token_cookie_after_full_flow(self):
        session = _build_session(inject_access_token=False)
        with pytest.raises(HelenAuthenticationException, match="no access-token"):
            session._do_full_login("user@example.com", "wrong-password")


class TestHtmlHelpers:
    def test_get_html_form_url_raises_on_missing_form(self):
        session = HelenSession()
        soup = BeautifulSoup("<html><body>no form here</body></html>", "html.parser")
        with pytest.raises(HelenAuthenticationException, match="expected a form"):
            session._get_html_form_url(soup)

    def test_get_html_link_url_raises_on_missing_link(self):
        session = HelenSession()
        soup = BeautifulSoup("<html><body>no link here</body></html>", "html.parser")
        with pytest.raises(HelenAuthenticationException, match="expected a link"):
            session._get_html_link_url(soup)

    def test_get_html_input_value_raises_on_missing_input(self):
        session = HelenSession()
        soup = BeautifulSoup("<form></form>", "html.parser")
        with pytest.raises(HelenAuthenticationException, match="expected hidden input 'code'"):
            session._get_html_input_value(soup, "code")


class TestFixUrl:
    def test_rewrites_stale_api_version(self):
        session = HelenSession()
        assert session._fix_url("https://api.omahelen.fi/v25/foo") == "https://api.oma.helen.fi/v21/foo"

    def test_rewrites_omahelen_domain(self):
        session = HelenSession()
        assert session._fix_url("https://api.omahelen.fi/v21/foo") == "https://api.oma.helen.fi/v21/foo"

    def test_leaves_already_correct_url_unchanged(self):
        session = HelenSession()
        assert session._fix_url("https://oma.helen.fi/v21/foo") == "https://oma.helen.fi/v21/foo"


class TestLogin:
    def test_exception_clears_session(self):
        session = HelenSession()
        with patch("helenservice.helen_session.Session"):
            with patch.object(HelenSession, "_do_full_login", side_effect=RuntimeError("network error")):
                with pytest.raises(HelenAuthenticationException):
                    session.login("user", "pass")
        assert session._session is None

    def test_get_access_token_raises_when_session_is_none(self):
        session = HelenSession()
        with pytest.raises(HelenAuthenticationException, match="not active"):
            session.get_access_token()


def _make_jwt(exp: int) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.sig"


class TestIsTokenValid:
    def test_returns_false_when_no_session(self):
        assert HelenSession().is_token_valid() is False

    def test_returns_false_when_no_access_token_cookie(self):
        session = HelenSession()
        session._session = MagicMock()
        session._session.cookies.get.return_value = None
        assert session.is_token_valid() is False

    def test_returns_true_when_token_not_expired(self):
        session = HelenSession()
        session._session = MagicMock()
        session._session.cookies.get.return_value = _make_jwt(int(time.time()) + 3600)
        assert session.is_token_valid() is True

    def test_returns_false_when_token_is_expired(self):
        session = HelenSession()
        session._session = MagicMock()
        session._session.cookies.get.return_value = _make_jwt(int(time.time()) - 1)
        assert session.is_token_valid() is False

    def test_returns_false_on_malformed_token(self):
        session = HelenSession()
        session._session = MagicMock()
        session._session.cookies.get.return_value = "not.a.jwt"
        assert session.is_token_valid() is False


class TestGetAllCookies:
    def test_returns_empty_when_no_session(self):
        assert HelenSession().get_all_cookies() == []

    def test_returns_cookie_tuples(self):
        session = HelenSession()
        mock_requests = MagicMock()
        session._session = mock_requests
        mock_cookie = MagicMock()
        mock_cookie.name = "access-token"
        mock_cookie.value = "tok-abc"
        mock_cookie.domain = "www.helen.fi"
        mock_cookie.path = "/"
        mock_requests.cookies.__iter__ = MagicMock(return_value=iter([mock_cookie]))
        assert session.get_all_cookies() == [("access-token", "tok-abc", "www.helen.fi", "/")]


class TestRefresh:
    def test_returns_false_for_empty_cookies(self):
        assert HelenSession().refresh([]) is False

    def test_success_returns_true_when_access_token_cookie_present(self):
        session = HelenSession()
        with patch("helenservice.helen_session.Session") as mock_session_cls:
            mock_requests = MagicMock()
            mock_session_cls.return_value = mock_requests
            mock_requests.cookies.get.return_value = "new-tok"

            result = session.refresh([
                ("refresh-token", "rt-abc", ".oma.helen.fi", "/"),
                ("access-token", "old-tok", ".oma.helen.fi", "/"),
            ])

        assert result is True
        get_call = mock_requests.get.call_args
        assert get_call.args[0] == HELEN_SESSION_RENEWAL_URL
        set_calls = [call.args[0] for call in mock_requests.cookies.set.call_args_list]
        assert "access-token" in set_calls

    def test_failure_when_no_access_token_cookie_after_get(self):
        session = HelenSession()
        with patch("helenservice.helen_session.Session") as mock_session_cls:
            mock_requests = MagicMock()
            mock_session_cls.return_value = mock_requests
            mock_requests.cookies.get.return_value = None

            result = session.refresh([("refresh-token", "rt-abc", ".oma.helen.fi", "/")])

        assert result is False
        assert session._session is None

    def test_failure_on_exception_returns_false(self):
        session = HelenSession()
        with patch("helenservice.helen_session.Session") as mock_session_cls:
            mock_requests = MagicMock()
            mock_session_cls.return_value = mock_requests
            mock_requests.get.side_effect = ConnectionError("network down")

            result = session.refresh([("refresh-token", "rt-abc", ".oma.helen.fi", "/")])

        assert result is False
        assert session._session is None

