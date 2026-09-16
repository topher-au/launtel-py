# launtel-py

HTTP client library for the Launtel residential customer portal
(`residential.launtel.net.au`). Logs in with your email/mobile + password,
parses services / usage / transactions / orders / profile pages into
dataclass models, and can persist the login cookie so repeat runs skip the
login flow.

## Install

```bash
pip install -e /opt/projects/launtel   # or: pip install launtel
```

Only dependencies: `requests`, `beautifulsoup4`, `dataclasses-json`.

## Usage

```python
from launtel import LauntelClient

with LauntelClient("you@example.com", "secret",
                   session_file="~/.launtel_cookies.txt") as client:
    account = client.get_account()       # balance + profile
    services = client.get_services()     # service cards
    usage = client.get_usage()           # monthly total + daily rows

print(account.balance)                   # 13.09
print(services[0].technology)            # Fibre Ultrafast
print(usage.total_gb)                    # 3075.36
print(client.get_transactions()[0].amount)
print(client.get_orders()[0].status)

open("services.json", "w").write(
    "[" + ",".join(s.to_json() for s in services) + "]")
```

Next run, the saved `session_id` cookie is reused — no login POST:

```python
with LauntelClient(session_file="~/.launtel_cookies.txt") as client:
    balance = client.get_account().balance
```

## How it works (verified against the live portal)

- `GET /services` while logged out → `302` to `/login?return_url=...`.
- `GET /login` issues the `session_id` cookie (`Secure`, `HttpOnly`, ~24h).
- Login is a form POST to `/login?return_url=%2F` with
  `username`, `password`, `return_url=/` (same fields as `#login-form`).
- Success lands on `/services?userid=N` — the id scopes every data page.
- Bad credentials → HTTP 200 with
  `Sorry incorrect login details` in `.alert-content` → `LauntelAuthError`.
- Section getters fetch only what they need: `get_account()` reads
  `/services` (service cards + balance card) and `/user_info` (name,
  email, mobile, referral code); `get_usage()`, `get_transactions()`
  and `get_orders()` each fetch their single page.

## API

| Method | Purpose |
|---|---|
| `login()` | Full login flow; raises `LauntelAuthError` on bad credentials |
| `ensure_login()` | Use current/saved cookie if valid, else `login()` |
| `is_authenticated()` | Cheap cookie-validity check (`GET /services`, no redirects) |
| `save_session()` / `load_session()` | Netscape-format cookie file (`chmod 600`, no passwords stored) |
| `get_page(path)` | Authenticated page fetch with one automatic re-login |
| `get_account()` | Fetch balance + profile → `Account` |
| `get_services()` | Fetch service cards → `list[Service]` |
| `get_usage(offset=0)` | Fetch usage → `Usage`; offset=N = N months prior |
| `get_transactions()` | Fetch billing ledger → `list[Transaction]` |
| `get_orders()` | Fetch order history → `list[Order]` |
| `keepalive()` | Ping `/session_alive` |
| `logout()` | Clear local cookies (and delete the session file) |

Models (`launtel.models`, all JSON-serializable): `Account`, `Service`,
`Usage` (+`UsageDay`), `Transaction`, `Order`.
Parsers are defensive — unknown markup yields `None`/`[]`, never exceptions.

## Tests

```bash
python3 -m unittest discover -s tests -v   # offline, no network
```

## GenAI Disclosure

See [AI_DISCLOSURE.md](AI_DISCLOSURE.md) — this project was written
with AI assistance (Hermes Agent) under the owner's direction.
