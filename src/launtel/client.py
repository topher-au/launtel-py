"""Authenticated HTTP client for the Launtel residential portal."""

from __future__ import annotations

import http.cookiejar as cookielib
import re
from pathlib import Path
from typing import Optional

import requests

from . import parsers
from .exceptions import (
    LauntelAuthError,
    LauntelError,
    LauntelNetworkError,
    LauntelSessionExpired,
)
from .models import Account, Order, Service, Transaction, Usage

DEFAULT_BASE_URL = "https://residential.launtel.net.au"
SESSION_COOKIE_NAME = "session_id"
LOGIN_PATH = "/login"
SERVICES_PATH = "/services"
USAGE_PATH = "/usage"
TRANSACTIONS_PATH = "/transactions"
ORDERS_PATH = "/orders"
USER_INFO_PATH = "/user_info"
KEEPALIVE_PATH = "/session_alive"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 "
    "launtel-py/0.1.0"
)


class LauntelClient:
    """Logs into the Launtel portal and fetches customer data.

    The portal authenticates with a ``session_id`` cookie that is issued
    on ``GET /login`` and validated on ``POST /login``. The cookie
    currently lives ~24h, so :meth:`save_session` / :meth:`load_session`
    let callers skip the login flow while the cookie is still valid::

        client = LauntelClient("you@example.com", "secret",
                               session_file="~/.launtel_cookies.txt")
        balance = client.get_account().balance
    """

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        session_file: Optional[str | Path] = None,
        timeout: float = 30.0,
        user_agent: str = DEFAULT_USER_AGENT,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.userid: Optional[str] = None  # portal user id, learned at login
        self.session_file = Path(session_file).expanduser() if session_file else None
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        # Pick up a previously saved cookie without hitting the network.
        if self.session_file and self.session_file.exists():
            try:
                self.load_session(validate=False)
            except LauntelError:  # corrupt/empty file: start clean
                pass

    # -- context manager --------------------------------------------------
    def __enter__(self) -> "LauntelClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        self.session.close()

    def _clear_cookie(self, name: str) -> None:
        """Remove every cookie with this name, whatever its domain/path.

        Direct ``jar.update({name: value})`` calls create domainless
        cookies that sit alongside the real domain-scoped one, so the
        session ends up sending two ``session_id`` headers. Always clear
        by name before (re)setting.
        """
        for cookie in [c for c in self.session.cookies if c.name == name]:
            try:
                self.session.cookies.clear(
                    domain=cookie.domain, path=cookie.path, name=cookie.name
                )
            except KeyError:
                pass  # already gone

    # -- authentication ---------------------------------------------------
    def login(
        self, username: Optional[str] = None, password: Optional[str] = None
    ) -> None:
        """Run the full login flow (GET login page, POST credentials).

        Raises:
            LauntelAuthError: credentials were rejected.
            LauntelNetworkError: transport-level failure.
        """
        username = username or self.username
        password = password or self.password
        if not username or not password:
            raise LauntelAuthError("username and password are required to log in")
        self.username, self.password = username, password

        try:
            # 1. Seed the session_id cookie (drop any stale/dup copies first).
            self._clear_cookie(SESSION_COOKIE_NAME)
            self.session.get(
                self.base_url + LOGIN_PATH,
                params={"return_url": "/"},
                timeout=self.timeout,
            )
            # 2. Submit the same fields as the portal's #login-form.
            response = self.session.post(
                self.base_url + LOGIN_PATH,
                params={"return_url": "/"},
                data={"username": username, "password": password,
                      "return_url": "/"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LauntelNetworkError(f"login request failed: {exc}") from exc

        if parsers.is_login_failure(response.text):
            raise LauntelAuthError("portal rejected the login details")
        if parsers.is_login_page(response.text):
            # Still on the login form but without the failure banner —
            # treat as a rejection rather than looping forever.
            raise LauntelAuthError("login did not succeed (still on login page)")
        # A successful login lands on /services?userid=N — remember it, as
        # every data page is scoped with ?userid=N.
        match = re.search(r"[?&]userid=(\d+)", response.url)
        if match:
            self.userid = match.group(1)
        if self.session_file:
            self.save_session()

    def logout(self) -> None:
        """Drop local cookies (the portal has no server-side logout link)."""
        self.session.cookies.clear()
        if self.session_file and self.session_file.exists():
            self.session_file.unlink()

    # -- session-cookie persistence ---------------------------------------
    @property
    def session_cookie(self) -> Optional[str]:
        """The current ``session_id`` cookie value, if present."""
        return self.session.cookies.get(SESSION_COOKIE_NAME)

    def save_session(self, path: Optional[str | Path] = None) -> Path:
        """Persist cookies to a Netscape-format cookie file.

        Returns the path written. Only the cookie values are stored —
        never the username or password.
        """
        target = Path(path).expanduser() if path else self.session_file
        if target is None:
            raise ValueError("no session file path given")
        jar = cookielib.MozillaCookieJar(str(target))
        # De-duplicate by name (last wins): the live jar can hold a
        # domainless copy next to the domain-scoped one, and saving both
        # would resurrect the duplicate on every load.
        latest: dict = {}
        for cookie in self.session.cookies:
            latest[cookie.name] = cookie
        for cookie in latest.values():
            jar.set_cookie(cookie)
        jar.save(ignore_discard=True, ignore_expires=True)
        target.chmod(0o600)
        self.session_file = target
        return target

    def load_session(
        self, path: Optional[str | Path] = None, validate: bool = True
    ) -> bool:
        """Load cookies from a file saved with :meth:`save_session`.

        Args:
            validate: when True (default), hit the portal to confirm the
                cookie is still accepted; expired/invalid cookies return
                False instead of raising.

        Returns True when a usable session is now in place.
        """
        target = Path(path).expanduser() if path else self.session_file
        if target is None or not target.exists():
            return False
        jar = cookielib.MozillaCookieJar(str(target))
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except Exception:
            return False
        # MozillaCookieJar drops session cookies on load only when
        # ignore_discard=False; we passed True, so session_id survives.
        # Clear same-named cookies first and copy with set_cookie (which
        # preserves domain/path) — a plain jar.update() would stack a
        # domainless duplicate next to the domain-scoped one.
        self._clear_cookie(SESSION_COOKIE_NAME)
        for cookie in jar:
            if not cookie.is_expired():
                self.session.cookies.set_cookie(cookie)
        if not self.session_cookie:
            return False
        self.session_file = target
        if validate and not self.is_authenticated():
            self.session.cookies.clear()
            return False
        return True

    def is_authenticated(self) -> bool:
        """True when the current cookies are accepted by the portal."""
        if not self.session_cookie:
            return False
        try:
            response = self.session.get(
                self.base_url + SERVICES_PATH,
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException:
            return False
        # Unauthenticated GET /services -> 302 to /login?return_url=...
        location = response.headers.get("Location", "")
        if response.status_code in (301, 302, 303, 307, 308):
            return "/login" not in location
        if parsers.is_login_page(response.text):
            return False
        # Harvest userid from the redirect target when we can.
        match = re.search(r"[?&]userid=(\d+)", location + response.url)
        if match:
            self.userid = match.group(1)
        return True

    def ensure_login(self) -> bool:
        """Make sure a valid session exists, logging in only if needed.

        Tries (in order): current cookies, the session file, the full
        login flow. Returns True; raises if everything fails.
        """
        if self.is_authenticated():
            return True
        if self.session_file and self.load_session(validate=True):
            return True
        self.login()
        if not self.is_authenticated():
            raise LauntelSessionExpired(
                "login flow completed but the portal still reports logged out"
            )
        return True

    def keepalive(self) -> bool:
        """Ping ``/session_alive``; True when the session is still valid."""
        try:
            response = self.session.get(
                self.base_url + KEEPALIVE_PATH, timeout=self.timeout
            )
            return response.status_code == 200 and bool(self.session_cookie)
        except requests.RequestException:
            return False

    # -- data fetching ----------------------------------------------------
    def _scoped(self, path: str) -> str:
        """Append ``?userid=N`` when known and not already present."""
        if self.userid and "userid=" not in path:
            sep = "&" if "?" in path else "?"
            return f"{path}{sep}userid={self.userid}"
        return path

    def _fetch_pages(self, paths: tuple[str, ...]) -> dict[str, str]:
        """Log in if needed and return ``{path: html}`` snapshots."""
        self.ensure_login()
        snapshots: dict[str, str] = {}
        for path in paths:
            try:
                snapshots[path] = self.get_page(path)
            except LauntelNetworkError:
                # A 404 (unknown page on some portal variants) just means
                # less data, not a failure — skip it.
                continue
        return snapshots

    @staticmethod
    def _page_key(snapshots: dict[str, str], prefix: str) -> Optional[str]:
        return next((k for k in snapshots if k.startswith(prefix)), None)

    def get_account(self) -> Account:
        """Fetch ``/services`` (balance) + ``/user_info`` (identity)."""
        snapshots = self._fetch_pages((SERVICES_PATH, USER_INFO_PATH))
        svc_key = self._page_key(snapshots, "/services")
        info_key = self._page_key(snapshots, "/user_info")
        if svc_key is None:
            return Account(username=self.username, userid=self.userid)
        return parsers.parse_account(
            snapshots[svc_key],
            snapshots.get(info_key, "") if info_key else "",
            username=self.username,
            userid=self.userid,
        )

    def get_services(self) -> list[Service]:
        """Fetch ``/services`` and return the service cards."""
        snapshots = self._fetch_pages((SERVICES_PATH,))
        key = self._page_key(snapshots, "/services")
        return parsers.parse_services(snapshots[key]) if key else []

    def get_usage(self, offset: int = 0) -> Usage:
        """Fetch ``/usage`` and return the monthly usage + daily rows.

        Args:
            offset: months prior to retrieve (0 = current month,
                1 = previous month, ...). The portal addresses history
                as ``/usage?locid=&offset=N``.
        """
        if isinstance(offset, bool) or not isinstance(offset, int):
            raise ValueError("offset must be an integer")
        if offset < 0:
            raise ValueError("offset must be 0 or greater")
        path = f"{USAGE_PATH}?locid=&offset={offset}" if offset else USAGE_PATH
        snapshots = self._fetch_pages((path,))
        key = self._page_key(snapshots, "/usage")
        return parsers.parse_usage(snapshots[key]) if key else Usage()

    def get_transactions(self) -> list[Transaction]:
        """Fetch ``/transactions`` and return the billing ledger."""
        snapshots = self._fetch_pages((TRANSACTIONS_PATH,))
        key = self._page_key(snapshots, "/transactions")
        return parsers.parse_transactions(snapshots[key]) if key else []

    def get_orders(self) -> list[Order]:
        """Fetch ``/orders`` and return the provisioning history."""
        snapshots = self._fetch_pages((ORDERS_PATH,))
        key = self._page_key(snapshots, "/orders")
        return parsers.parse_orders(snapshots[key]) if key else []

    def get_page(self, path: str) -> str:
        """Fetch an authenticated portal page and return its HTML.

        Transparently (re-)logs in once when the session has expired.
        """
        path = self._scoped(path)
        try:
            response = self.session.get(
                self.base_url + path, timeout=self.timeout
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LauntelNetworkError(f"GET {path} failed: {exc}") from exc
        if parsers.is_login_page(response.text):
            # Session died mid-use: exactly one re-login attempt.
            self.session.cookies.clear()
            try:
                self.login()
            except LauntelAuthError as exc:
                raise LauntelSessionExpired(
                    "saved session expired and re-login failed"
                ) from exc
            try:
                response = self.session.get(
                    self.base_url + path, timeout=self.timeout
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                raise LauntelNetworkError(f"GET {path} failed: {exc}") from exc
            if parsers.is_login_page(response.text):
                raise LauntelSessionExpired(
                    "still logged out after re-login"
                )
        if not self.userid:
            # Harvest ?userid=N from page links (cookie-reuse path never
            # saw the post-login redirect that normally reveals it).
            match = re.search(r"[?&]userid=(\d+)", response.text)
            if match:
                self.userid = match.group(1)
        return response.text
