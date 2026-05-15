from __future__ import annotations

import base64
import json
import logging
import re
import time

from bs4 import BeautifulSoup
from requests import Response, Session

from helenservice.api_exceptions import HelenAuthenticationException

from .const import HELEN_AUTH_ENDPOINT, HELEN_AUTH_PARAMS, HELEN_CLIENT_ID, HELEN_LOGIN_API_VERSION, HELEN_TOKEN_ENDPOINT, HTTP_READ_TIMEOUT

logger = logging.getLogger(__name__)


class HelenSession:
    HELEN_LOGIN_HOST = "https://login.helen.fi"

    def __init__(self) -> None:
        self._session: Session | None = None

    def login(self, username: str, password: str) -> HelenSession:
        """Login to Oma Helen and extract the access-token cookie."""
        self._session = Session()
        logger.debug("Logging in to Oma Helen")
        try:
            self._do_full_login(username, password)
        except Exception as exception:
            logger.exception("Login to Oma Helen failed. Check your credentials!")
            self._session.close()
            self._session = None
            raise HelenAuthenticationException(exception) from exception
        logger.debug("Logged in to Oma Helen")
        return self

    def get_access_token(self) -> str:
        """Get the access-token to use the Helen API."""
        if self._session is None:
            raise HelenAuthenticationException("The session is not active. Log in first")
        access_token = self._session.cookies.get("access-token")
        if access_token is None:
            raise HelenAuthenticationException("No access token found. Log in first")
        return access_token

    def is_token_valid(self) -> bool:
        """Return True if the access-token JWT is present and not yet expired."""
        if self._session is None:
            return False
        token = self._session.cookies.get("access-token")
        if not token:
            return False
        try:
            payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
            return payload["exp"] > time.time()
        except Exception:
            return False

    def get_refresh_token(self) -> str | None:
        """Get the refresh-token cookie if present."""
        if self._session is None:
            return None
        return self._session.cookies.get("refresh-token")

    def refresh(self, refresh_token: str) -> bool:
        """Exchange a refresh token for a new access token. Returns True on success, False on any failure."""
        self._session = Session()
        try:
            response = self._session.post(
                HELEN_TOKEN_ENDPOINT,
                data={"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": HELEN_CLIENT_ID},
                timeout=HTTP_READ_TIMEOUT,
            )
            if not response.ok:
                logger.debug("Token refresh failed: status=%s", response.status_code)
                self._session.close()
                self._session = None
                return False
            token_data = response.json()
            new_access_token = token_data.get("access_token")
            if not new_access_token:
                logger.debug("Token refresh response missing access_token")
                self._session.close()
                self._session = None
                return False
            self._session.cookies.set("access-token", new_access_token, domain="omahelen.fi")
            new_refresh_token = token_data.get("refresh_token")
            if new_refresh_token:
                self._session.cookies.set("refresh-token", new_refresh_token, domain="helen.fi")
            logger.debug("Token refresh successful")
            return True
        except Exception:
            logger.debug("Token refresh failed with exception", exc_info=True)
            if self._session:
                self._session.close()
            self._session = None
            return False

    def close(self) -> None:
        """Close the session for the Oma Helen web service."""
        if self._session is not None:
            self._session.close()
            self._session = None
            logger.debug("HelenSession was closed")

    def _do_full_login(self, username: str, password: str) -> None:
        """Drive the full Ubisecure OAuth login flow:
        auth endpoint → login form → credentials → Continue form → token exchange.
        """
        # Step 1: POST to auth endpoint → login form
        auth_soup = self._post_and_parse(HELEN_AUTH_ENDPOINT, params=HELEN_AUTH_PARAMS)
        login_url = self.HELEN_LOGIN_HOST + self._get_html_form_url(auth_soup)
        logger.debug("Login form URL: %s", login_url)

        # Step 2: POST credentials → Continue form (OAuth code + state hidden fields)
        credentials_soup = self._post_and_parse(login_url, data={"username": username, "password": password})

        # Step 3: Submit Continue form → page with a link
        proceed_response = self._get_with_oauth_code(credentials_soup)
        logger.debug("Proceed: status=%s url=%s", proceed_response.status_code, proceed_response.url)

        # Step 4: Follow the link → second OAuth code exchange form
        proceed_soup = BeautifulSoup(proceed_response.text, "html.parser")
        auth2_url = self._fix_url(self._get_html_link_url(proceed_soup))
        logger.debug("Auth2 URL: %s", auth2_url)

        auth2_soup = self._get_and_parse(auth2_url)

        # Step 5: Submit second OAuth code exchange → access-token cookie is set
        final_response = self._get_with_oauth_code(auth2_soup)
        logger.debug("Final: status=%s url=%s", final_response.status_code, final_response.url)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Cookies after login: %s", {c.name: c.domain for c in self._session.cookies})

        if self._session.cookies.get("access-token") is None:
            raise HelenAuthenticationException(
                "Login failed: no access-token cookie received. Check your credentials."
            )

    def _post_and_parse(self, url: str, *, data: dict | None = None, params: dict | None = None) -> BeautifulSoup:
        response = self._session.post(url, data=data, params=params, timeout=HTTP_READ_TIMEOUT)
        logger.debug("POST %s → status=%s url=%s", url, response.status_code, response.url)
        return BeautifulSoup(response.text, "html.parser")

    def _get_and_parse(self, url: str) -> BeautifulSoup:
        response = self._session.get(url, timeout=HTTP_READ_TIMEOUT)
        logger.debug("GET %s → status=%s url=%s", url, response.status_code, response.url)
        return BeautifulSoup(response.text, "html.parser")

    def _get_with_oauth_code(self, soup: BeautifulSoup) -> Response:
        """GET the form action URL with OAuth code+state extracted from hidden inputs."""
        url = self._get_html_form_url(soup)
        code = self._get_html_input_value(soup, "code")
        state = self._get_html_input_value(soup, "state")
        return self._session.get(url, params={"code": code, "state": state}, timeout=HTTP_READ_TIMEOUT)

    def _fix_url(self, url: str) -> str:
        """Normalise a URL from the OAuth flow that may carry a stale API version
        or the legacy 'omahelen' domain instead of 'oma.helen'.
        """
        url = re.sub(r"/v\d+/", f"/{HELEN_LOGIN_API_VERSION}/", url)
        return url.replace("omahelen", "oma.helen")

    def _get_html_form_url(self, soup: BeautifulSoup) -> str:
        form = soup.find("form")
        if form is None:
            raise HelenAuthenticationException("Login flow broken: expected a form but none was found in response")
        return form.attrs["action"]

    def _get_html_link_url(self, soup: BeautifulSoup) -> str:
        link = soup.find("a")
        if link is None:
            raise HelenAuthenticationException("Login flow broken: expected a link but none was found in response")
        return link.attrs["href"]

    def _get_html_input_value(self, soup: BeautifulSoup, name: str) -> str:
        element = soup.find("input", {"name": name})
        if element is None:
            raise HelenAuthenticationException(
                f"Login flow broken: expected hidden input '{name}' but it was not found in response"
            )
        return element.get("value")
