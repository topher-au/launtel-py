"""Data models for customer data parsed out of the Launtel portal.

All models use ``dataclasses_json`` so snapshots serialize cleanly::

    svc.to_json()          # str
    svc.to_dict()          # plain dict
    Service.from_json(raw)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from dataclasses_json import dataclass_json


@dataclass_json
@dataclass
class Account:
    """The customer account: identity (``/user_info``) + balance (services page)."""

    userid: Optional[str] = None
    username: Optional[str] = None  # email or mobile used at login
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None
    referral_code: Optional[str] = None
    balance: Optional[float] = None  # current balance (AUD)
    charge_today: Optional[float] = None
    charge_tomorrow: Optional[float] = None
    days_remaining: Optional[int] = None
    currency: str = "AUD"

    @property
    def name(self) -> Optional[str]:
        parts = [p for p in (self.first_name, self.last_name) if p]
        return " ".join(parts) or None


@dataclass_json
@dataclass
class Service:
    """One internet service card from the services page."""

    id: Optional[str] = None  # portal service id, e.g. "261873"
    name: Optional[str] = None  # custom label, e.g. "Home - Port 2"
    status: Optional[str] = None  # e.g. "Active - Router online"
    technology: Optional[str] = None  # e.g. "Fibre Ultrafast"
    speed_down_mbps: Optional[float] = None
    speed_up_mbps: Optional[float] = None
    address: Optional[str] = None  # full connection address
    provider: Optional[str] = None  # infrastructure provider, e.g. "nbn"
    avc_id: Optional[str] = None  # e.g. "AVC000215219580"
    daily_price: Optional[float] = None
    ntd_port: Optional[str] = None
    ipv4: Optional[str] = None
    ipv4_ptr: Optional[str] = None
    ipv6_prefix: Optional[str] = None


@dataclass_json
@dataclass
class UsageDay:
    """One row of the daily usage table."""

    day: Optional[int] = None
    download_gb: Optional[float] = None
    upload_gb: Optional[float] = None
    free_gb: Optional[float] = None
    avg30_gb: Optional[float] = None


@dataclass_json
@dataclass
class Usage:
    """Data usage for the current month (``/usage`` page)."""

    period: Optional[str] = None  # e.g. "September 2026"
    total_gb: Optional[float] = None
    daily: List[UsageDay] = field(default_factory=list)


@dataclass_json
@dataclass
class Transaction:
    """One row of the transactions ledger."""

    date: Optional[str] = None
    description: Optional[str] = None
    billed_for: Optional[str] = None
    amount: Optional[float] = None
    balance: Optional[float] = None


@dataclass_json
@dataclass
class Order:
    """One row of the order history (``/orders`` page)."""

    order_id: Optional[str] = None
    date: Optional[str] = None
    updated: Optional[str] = None
    avc_id: Optional[str] = None
    speed: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
