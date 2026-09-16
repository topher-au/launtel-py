"""Quickstart example: fetch sections of your Launtel customer data."""

import getpass

from launtel import LauntelClient

EMAIL = input("Launtel email/mobile: ")
PASSWORD = getpass.getpass("Launtel password: ")

with LauntelClient(EMAIL, PASSWORD,
                   session_file="~/.launtel_cookies.txt") as client:
    # Each getter logs in only when the saved cookie is missing/expired,
    # and fetches only the pages its section needs.
    account = client.get_account()
    services = client.get_services()
    usage = client.get_usage()
    transactions = client.get_transactions()
    orders = client.get_orders()

print(f"Account : {account.name} <{account.email}> {account.mobile}")
print(f"Balance : ${account.balance} {account.currency} "
      f"(today ${account.charge_today}, "
      f"tomorrow ${account.charge_tomorrow}, "
      f"{account.days_remaining} days left)")
for svc in services:
    print(f"Service : {svc.name} | {svc.status} | {svc.technology} "
          f"{svc.speed_down_mbps}/{svc.speed_up_mbps} Mbps | "
          f"${svc.daily_price}/day | {svc.ipv4}")
print(f"Usage   : {usage.total_gb} GB ({usage.period}, "
      f"{len(usage.daily)} days)")
print(f"Ledger  : {len(transactions)} transactions, {len(orders)} orders")

# Second run reuses ~/.launtel_cookies.txt with no login POST at all:
#   with LauntelClient(session_file="~/.launtel_cookies.txt") as c:
#       print(c.get_account().balance)

# Snapshot a section to disk:
#   open("services.json", "w").write(
#       "[" + ",".join(s.to_json() for s in services) + "]")
