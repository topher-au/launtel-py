"""Parsers that turn portal HTML pages into :mod:`launtel.models`.

Targets the real markup of ``residential.launtel.net.au`` (verified
Sept 2026): service cards with ``dl.service-dl`` definition lists, the
``card-balance`` widget, ``input[name=...]`` fields on ``/user_info``,
and plain ``<table>`` ledgers on ``/transactions``, ``/orders`` and
``/usage``.

Parsing is done with BeautifulSoup; everything is defensive —
unexpected markup yields ``None`` / ``[]``, never exceptions.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .models import (
    Account,
    Order,
    Service,
    Transaction,
    Usage,
    UsageDay,
)

#: Marker shown inside ``.alert-content`` when credentials are rejected.
LOGIN_FAILURE_MARKER = "sorry incorrect login details"

#: Trailing address token recognised as the infrastructure provider.
PROVIDERS = frozenset({
    "nbn", "vocus", "opticomm", "redtrain", "redtrains",
    "lbnco", "opennetworks", "dgttek", "telstra",
})


def _soup(html_doc: str) -> BeautifulSoup:
    return BeautifulSoup(html_doc, "html.parser")


def _text(element) -> str:
    """Whitespace-collapsed text of a tag (or ``""`` for None)."""
    if element is None:
        return ""
    return re.sub(r"\s+", " ", element.get_text(" ")).strip()


def page_text(html_doc: str) -> str:
    """Return the visible text of a page, whitespace-collapsed."""
    soup = _soup(html_doc)
    for tag in soup(["script", "style"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def page_tables(html_doc: str) -> list[list[list[str]]]:
    """Return every ``<table>`` on the page as rows of cell strings."""
    tables: list[list[list[str]]] = []
    for table in _soup(html_doc).find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [_text(c) for c in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def is_login_page(html_doc: str) -> bool:
    """True when the HTML is the portal login form."""
    soup = _soup(html_doc)
    return bool(
        soup.find(id="login-form")
        or (soup.find("input", attrs={"name": "username"})
            and soup.find("input", attrs={"name": "password"}))
    )


def is_login_failure(html_doc: str) -> bool:
    """True when the page reports rejected credentials."""
    return LOGIN_FAILURE_MARKER in html_doc.lower()


def _money(raw: str | None) -> float | None:
    """Parse ``+$13.09`` / ``-$4.40`` / ``$0.00`` → float."""
    if not raw:
        return None
    match = re.search(r"([+-]?)\$([\d,]+\.\d{2})", raw.replace(" ", ""))
    if not match:
        return None
    value = float(match.group(2).replace(",", ""))
    return -value if match.group(1) == "-" else value


def _dl_pairs(scope, dl_class: str) -> dict[str, str]:
    """Map ``dt → dd`` text for ``<dl class="...">`` blocks in scope."""
    pairs: dict[str, str] = {}
    for dl in scope.find_all("dl", class_=dl_class):
        for dt in dl.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if dd is not None:
                pairs[_text(dt)] = _text(dd)
    return pairs


def _input_value(html_doc: str, name: str) -> str | None:
    """Value of ``<input name="...">``."""
    tag = _soup(html_doc).find("input", attrs={"name": name})
    if tag is None:
        return None
    return tag.get("value") or None


# -- account --------------------------------------------------------------

_BALANCE_LABELS = {
    "Current Balance": "balance",
    "Today's Charge": "charge_today",
    "Tomorrow's Charge": "charge_tomorrow",
}


def parse_account(
    services_html: str,
    user_info_html: str = "",
    username: str | None = None,
    userid: str | None = None,
) -> Account:
    """Account identity from ``/user_info`` + balance from services page."""
    account = Account(username=username, userid=userid)
    if user_info_html:
        account.first_name = _input_value(user_info_html, "firstname")
        account.last_name = _input_value(user_info_html, "lastname")
        account.email = _input_value(user_info_html, "email")
        account.mobile = _input_value(user_info_html, "mobno")
        account.referral_code = _input_value(user_info_html, "myrefercode")
    pairs = _dl_pairs(_soup(services_html), "balance-dl")
    for label, field_name in _BALANCE_LABELS.items():
        for dt, dd in pairs.items():
            if dt.startswith(label):
                setattr(account, field_name, _money(dd))
    days = re.search(
        r"Estimated Days Remaining\s*(\d+)", page_text(services_html)
    )
    if days:
        account.days_remaining = int(days.group(1))
    return account


# -- services ---------------------------------------------------------------

_SPEED_RE = re.compile(
    r"\(\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*\)"
)
_MODIFY_RE = re.compile(r"modifyService\((\d+)(?:,\s*'([^']+)')?")


def _card_scope(title_tag) -> BeautifulSoup:
    """HTML between this card title and the next card heading."""
    chunks: list[str] = []
    for element in title_tag.find_all_next():
        if getattr(element, "name", None) == "h2":
            break
        chunks.append(str(element))
    return _soup("".join(chunks))


def parse_services(html_doc: str) -> list[Service]:
    """One :class:`Service` per ``h2.service-title`` card."""
    services: list[Service] = []
    soup = _soup(html_doc)
    for title in soup.find_all("h2", class_="service-title"):
        scope = _card_scope(title)
        fields = _dl_pairs(scope, "service-dl")
        status = fields.get("Status")
        tech_speed = fields.get("Technology / Speed", "")
        tech = tech_speed.split("(")[0].strip() or None
        down = up = None
        match = _SPEED_RE.search(tech_speed)
        if match:
            down, up = float(match.group(1)), float(match.group(2))
        # "..., TAS 7248 nbn" → address + trailing provider token.
        addr_prov = fields.get(
            "Connection address & Infrastructure Provider", ""
        )
        address, provider = addr_prov, None
        parts = addr_prov.rsplit(None, 1)
        if len(parts) == 2 and parts[1].lower() in PROVIDERS:
            address, provider = parts
        address = address.strip() or None
        svc_id = avc = None
        modifier = scope.find(attrs={"onclick": _MODIFY_RE})
        if modifier is not None:
            found = _MODIFY_RE.search(modifier["onclick"])
            if found:
                svc_id, avc = found.group(1), found.group(2)
        ipv4 = fields.get("IPv4", "")
        services.append(
            Service(
                id=svc_id,
                name=_text(title) or None,
                status=status,
                technology=tech,
                speed_down_mbps=down,
                speed_up_mbps=up,
                address=address,
                provider=provider,
                avc_id=avc or fields.get("Connection ID"),
                daily_price=_money(fields.get("Daily Price")),
                ntd_port=fields.get("NTD Port"),
                ipv4=ipv4.split(" ")[0] or None,
                ipv4_ptr=fields.get("IPv4 PTR"),
                ipv6_prefix=fields.get("IPv6 Prefix"),
            )
        )
    return services


# -- generic ledger tables ----------------------------------------------------

def _ledger(
    html_doc: str, required: set[str]
) -> tuple[list[str], list[list[str]]]:
    """Header + rows of the first table containing all ``required`` headers."""
    for table in page_tables(html_doc):
        if not table:
            continue
        header = [cell.strip() for cell in table[0]]
        if required.issubset(set(header)):
            return header, table[1:]
    return [], []


def parse_transactions(html_doc: str) -> list[Transaction]:
    header, rows = _ledger(
        html_doc, {"Transaction Date (Local)", "Amount", "Balance"}
    )
    out: list[Transaction] = []
    for row in rows:
        cells = dict(zip(header, row))
        if not any(cells.values()):
            continue
        out.append(
            Transaction(
                date=cells.get("Transaction Date (Local)") or None,
                description=cells.get("Description") or None,
                billed_for=cells.get("Date Billed For") or None,
                amount=_money(cells.get("Amount")),
                balance=_money(cells.get("Balance")),
            )
        )
    return out


def parse_orders(html_doc: str) -> list[Order]:
    header, rows = _ledger(html_doc, {"WSP Order ID", "Status"})
    out: list[Order] = []
    for row in rows:
        cells = dict(zip(header, row))
        if not cells.get("WSP Order ID"):
            continue
        out.append(
            Order(
                order_id=cells.get("WSP Order ID"),
                date=cells.get("Date") or None,
                updated=cells.get("Updated") or None,
                avc_id=cells.get("AVC ID") or None,
                speed=cells.get("Speed") or None,
                type=cells.get("Type") or None,
                status=cells.get("Status") or None,
            )
        )
    return out


# -- usage --------------------------------------------------------------------

def parse_usage(html_doc: str) -> Usage:
    """Period + total + daily rows from the ``/usage`` page."""
    text = page_text(html_doc)
    usage = Usage()
    match = re.search(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{4})\s*-\s*Total Usage\s*"
        r"([\d.]+)\s*GB",
        text,
    )
    if match:
        usage.period = f"{match.group(1)} {match.group(2)}"
        usage.total_gb = float(match.group(3))
    header, rows = _ledger(html_doc, {"Day of month", "Download GB"})
    for row in rows:
        cells = dict(zip(header, row))
        try:
            day = int(cells.get("Day of month", "").strip())
        except ValueError:
            continue
        num = lambda key: (  # noqa: E731
            float(cells[key]) if cells.get(key, "").strip() else None
        )
        usage.daily.append(
            UsageDay(
                day=day,
                download_gb=num("Download GB"),
                upload_gb=num("Upload GB"),
                free_gb=num("Free GB"),
                avg30_gb=num("30 day average GB"),
            )
        )
    return usage
