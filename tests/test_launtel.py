"""Offline unit tests for the launtel library (no network access)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from launtel import (
    LauntelAuthError,
    LauntelClient,
    LauntelSessionExpired,
)
from launtel import parsers
from launtel.models import Account, Service, Usage

LOGIN_PAGE = """
<html><body><form role="form" method="post" id="login-form">
<input name="username" type="text">
<input name="password" type="password">
<input type="hidden" name="return_url" value="/">
</form></body></html>
"""

FAILURE_PAGE = LOGIN_PAGE.replace(
    "</form>",
    '</form><div name="main_page_alert"><div class="alert alert-warning">'
    '<div class="alert-content">Sorry incorrect login details</div>'
    "</div></div>",
)

SERVICES_PAGE = """
<html><body>
<h2 class="card-title service-title"><span class="service-title-txt">Home</span> - Port 2</h2>
<dl class="service-dl">
<div><dt>Status</dt><dd class="dd-large order-status order-status-complete">Active - Router online</dd></div>
<div><dt>Technology / Speed</dt><dd class="dd-large">Fibre Ultrafast (1000/100)</dd></div>
<div class="service-dg"><dt>Connection address & Infrastructure Provider</dt>
<dd>Unit 4, 9 Norman Court, Newnham, TAS 7248<br>nbn</dd></div>
<div><dt>Connection ID</dt><dd>AVC000215219580</dd></div>
<div><dt>Daily Price</dt><dd>$4.40</dd></div>
<div><dt>NTD Port</dt><dd>UNI-D Port 2</dd></div>
<div><dt>IPv4</dt><dd>144.48.164.141 (Real world routable)</dd></div>
<div><dt>IPv4 PTR</dt><dd>topher.au</dd></div>
<div><dt>IPv6 Prefix</dt><dd>2404:e80:fce::/48</dd></div>
</dl>
<button name="service261873_modify" onclick="modifyService(261873,'AVC000215219580')">Modify Service</button>
<div class="card card-balance"><div class="card-body"><dl class="balance-dl">
<div class="balance-dg"><dt>Current Balance</dt><dd><span class="text-success">+$13.09</span></dd></div>
<div class="balance-dg"><dt>Today's Charge</dt><dd><span class="text-success">$0.00</span></dd></div>
<div class="balance-dg"><dt>Tomorrow's Charge</dt><dd><span class="text-danger">$4.55</span></dd></div>
</dl><p>Estimated Days Remaining 2</p></div></div>
</body></html>
"""

USER_INFO_PAGE = """
<html><body>
<input type="text" name="firstname" value="Topher" readonly>
<input type="text" name="lastname" value="Sheridan" readonly>
<input type="email" name="email" value="topher@topher.au">
<input type="number" name="mobno" value="0400298907">
<input type="text" name="myrefercode" value="OCPTG" disabled>
</body></html>
"""

USAGE_PAGE = """
<html><body><p>September 2026 - Total Usage 3075.36GB</p>
<table><tr><th>Day of month</th><th>Download GB</th><th>Upload GB</th>
<th>Free GB</th><th>30 day average GB</th></tr>
<tr><td>01</td><td>39.68</td><td>10.85</td><td>0.00</td><td>122.61</td></tr>
<tr><td>02</td><td>55.58</td><td>25.71</td><td>0.00</td><td>118.73</td></tr>
</table></body></html>
"""

TRANSACTIONS_PAGE = """
<html><body><table>
<tr><th>Transaction Date (Local)</th><th>Description</th><th>Date Billed For</th>
<th></th><th></th><th></th><th>Amount</th><th>Balance</th></tr>
<tr><td>16 September 2026 02:35</td><td>Static real-world IPv4 address</td>
<td>16 Sep 2026</td><td></td><td></td><td></td><td>-$0.15</td><td>$13.09</td></tr>
</table></body></html>
"""

ORDERS_PAGE = """
<html><body><table>
<tr><th>WSP Order ID</th><th>Date</th><th>Updated</th><th>AVC ID</th>
<th>Speed</th><th>Type</th><th>Status</th><th></th></tr>
<tr><td>ORD010264183245</td><td>06-08-2026 23:12:52</td><td>06-08-2026 23:19:15</td>
<td>AVC000215219580</td><td>1000/100 Mbps</td><td>Modify</td><td>Complete</td><td></td></tr>
</table></body></html>
"""


def _response(text="", status=200, headers=None, url=""):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status
    resp.headers = headers or {}
    resp.url = url
    return resp


class TestParsers(unittest.TestCase):
    def test_login_failure_detection(self):
        self.assertTrue(parsers.is_login_failure(FAILURE_PAGE))
        self.assertFalse(parsers.is_login_failure(LOGIN_PAGE))
        self.assertFalse(parsers.is_login_failure(SERVICES_PAGE))

    def test_login_page_detection(self):
        self.assertTrue(parsers.is_login_page(LOGIN_PAGE))
        self.assertTrue(parsers.is_login_page(FAILURE_PAGE))
        self.assertFalse(parsers.is_login_page(SERVICES_PAGE))

    def test_parse_account(self):
        account = parsers.parse_account(
            SERVICES_PAGE, USER_INFO_PAGE,
            username="topher@topher.au", userid="1836",
        )
        self.assertEqual(account.email, "topher@topher.au")
        self.assertEqual(account.mobile, "0400298907")
        self.assertEqual(account.name, "Topher Sheridan")
        self.assertEqual(account.referral_code, "OCPTG")
        self.assertEqual(account.balance, 13.09)
        self.assertEqual(account.charge_today, 0.0)
        self.assertEqual(account.charge_tomorrow, 4.55)
        self.assertEqual(account.days_remaining, 2)

    def test_parse_usage(self):
        usage = parsers.parse_usage(USAGE_PAGE)
        self.assertEqual(usage.period, "September 2026")
        self.assertAlmostEqual(usage.total_gb, 3075.36)
        self.assertEqual(len(usage.daily), 2)
        self.assertAlmostEqual(usage.daily[0].download_gb, 39.68)

    def test_parse_services(self):
        services = parsers.parse_services(SERVICES_PAGE)
        self.assertEqual(len(services), 1)
        svc = services[0]
        self.assertEqual(svc.id, "261873")
        self.assertEqual(svc.technology, "Fibre Ultrafast")
        self.assertEqual(svc.speed_down_mbps, 1000)
        self.assertEqual(svc.speed_up_mbps, 100)
        self.assertEqual(svc.avc_id, "AVC000215219580")
        self.assertEqual(svc.daily_price, 4.4)
        self.assertEqual(svc.ipv4, "144.48.164.141")
        self.assertEqual(svc.provider, "nbn")

    def test_parse_transactions(self):
        txns = parsers.parse_transactions(TRANSACTIONS_PAGE)
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].amount, -0.15)
        self.assertEqual(txns[0].balance, 13.09)

    def test_parse_orders(self):
        orders = parsers.parse_orders(ORDERS_PAGE)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].order_id, "ORD010264183245")
        self.assertEqual(orders[0].status, "Complete")

    def test_parse_account_combines_pages(self):
        account = parsers.parse_account(
            SERVICES_PAGE, USER_INFO_PAGE,
            username="topher@topher.au", userid="1836",
        )
        self.assertEqual(account.balance, 13.09)
        self.assertEqual(account.email, "topher@topher.au")
        self.assertEqual(account.userid, "1836")


class TestClientLogin(unittest.TestCase):
    def _client(self, get=None, post=None):
        client = LauntelClient("jane@example.com", "secret")
        client.session = MagicMock()
        # real cookie jar behaviour for session_id checks
        import requests

        client.session.cookies = requests.cookies.RequestsCookieJar()
        client.session.get.side_effect = get or []
        client.session.post.side_effect = post or []
        return client

    def test_login_posts_form_fields(self):
        client = self._client(
            get=[_response(LOGIN_PAGE)],
            post=[_response(SERVICES_PAGE,
                            url="https://residential.launtel.net.au/services?userid=1836")],
        )
        client.is_authenticated = lambda: True  # skip live validation
        client.login()
        args, kwargs = client.session.post.call_args
        self.assertTrue(args[0].endswith("/login"))
        self.assertEqual(
            kwargs["data"],
            {"username": "jane@example.com", "password": "secret",
             "return_url": "/"},
        )
        self.assertEqual(client.userid, "1836")

    def test_login_failure_raises(self):
        client = self._client(
            get=[_response(LOGIN_PAGE)],
            post=[_response(FAILURE_PAGE)],
        )
        with self.assertRaises(LauntelAuthError):
            client.login()

    def test_is_authenticated_false_on_login_redirect(self):
        client = self._client(
            get=[_response("", status=302,
                           headers={"Location": "/login?return_url=%2F"})]
        )
        client.session.cookies.set("session_id", "abc123")
        self.assertFalse(client.is_authenticated())

    def test_is_authenticated_true_on_dashboard(self):
        client = self._client(get=[_response(SERVICES_PAGE)])
        client.session.cookies.set("session_id", "abc123")
        self.assertTrue(client.is_authenticated())

    def test_get_page_relogs_in_once_on_expiry(self):
        client = self._client(
            get=[_response(LOGIN_PAGE), _response(LOGIN_PAGE),
                 _response(USAGE_PAGE)],
            post=[_response(SERVICES_PAGE,
                            url="https://residential.launtel.net.au/services?userid=1836")],
        )
        client.is_authenticated = lambda: True
        html = client.get_page("/usage")
        self.assertIn("Download", html)
        client.session.post.assert_called_once()  # exactly one re-login

    def test_get_page_raises_when_relogin_fails(self):
        client = self._client(
            get=[_response(LOGIN_PAGE), _response(LOGIN_PAGE)],
            post=[_response(FAILURE_PAGE)],
        )
        with self.assertRaises(LauntelSessionExpired):
            client.get_page("/usage")


class TestSessionPersistence(unittest.TestCase):
    def test_save_load_roundtrip(self):
        import requests

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cookies.txt"
            writer = LauntelClient("jane@example.com", "secret",
                                   session_file=path)
            writer.session = MagicMock()
            writer.session.cookies = requests.cookies.RequestsCookieJar()
            writer.session.cookies.set(
                "session_id", "test-cookie-value",
                domain="residential.launtel.net.au", path="/",
            )
            writer.save_session()
            self.assertTrue(path.exists())
            # Password must never end up in the cookie file.
            self.assertNotIn("secret", path.read_text())

            reader = LauntelClient(session_file=path)
            reader.session = MagicMock()
            reader.session.cookies = requests.cookies.RequestsCookieJar()
            ok = reader.load_session(validate=False)
            self.assertTrue(ok)
            self.assertEqual(reader.session_cookie, "test-cookie-value")

    def test_load_replaces_duplicate_session_id(self):
        import requests

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cookies.txt"
            writer = LauntelClient(session_file=path)
            writer.session = MagicMock()
            writer.session.cookies = requests.cookies.RequestsCookieJar()
            writer.session.cookies.set(
                "session_id", "fresh-value",
                domain="residential.launtel.net.au", path="/",
            )
            writer.save_session()

            reader = LauntelClient(session_file=path)
            reader.session = MagicMock()
            reader.session.cookies = requests.cookies.RequestsCookieJar()
            # Simulate the old bug: a stale domainless copy in the jar.
            reader.session.cookies.set("session_id", "stale-value")
            self.assertTrue(reader.load_session(validate=False))
            matches = [c for c in reader.session.cookies
                       if c.name == "session_id"]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].value, "fresh-value")

    def test_load_missing_file_returns_false(self):
        client = LauntelClient()
        self.assertFalse(client.load_session("/nonexistent/cookies.txt"))

    def test_cookie_file_permissions(self):
        import requests

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cookies.txt"
            client = LauntelClient(session_file=path)
            client.session = MagicMock()
            client.session.cookies = requests.cookies.RequestsCookieJar()
            client.session.cookies.set("session_id", "x")
            client.save_session()
            self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")


class TestSerialization(unittest.TestCase):
    def test_section_models_json_roundtrip(self):
        account = parsers.parse_account(
            SERVICES_PAGE, USER_INFO_PAGE, userid="1836")
        self.assertEqual(
            Account.from_json(account.to_json()).balance, 13.09)
        usage = parsers.parse_usage(USAGE_PAGE)
        self.assertAlmostEqual(
            Usage.from_json(usage.to_json()).total_gb, 3075.36)
        txns = parsers.parse_transactions(TRANSACTIONS_PAGE)
        self.assertEqual(len(txns), 1)

    def test_individual_models_serialize(self):
        for obj in (Account(email="a@b.com"), Service(technology="Fibre"),
                    Usage(total_gb=1.5)):
            self.assertEqual(type(obj).from_json(obj.to_json()), obj)


if __name__ == "__main__":
    unittest.main()
