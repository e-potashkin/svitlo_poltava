"""Tests for poe_gpv.py, the operator page parser.

Run: python3 tests/test_poe_gpv.py
No Home Assistant needed: the module is loaded by path and the page comes from
tests/fixtures (a real 2026-10-20 response).
"""

import importlib.util
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_components" / "svitlo_poltava" / "poe_gpv.py"
FIXTURE = ROOT / "tests" / "fixtures" / "poe_gpv_2026-10-20.html"
NEW_FIXTURE = ROOT / "tests" / "fixtures" / "poe_gpv_2026-10-28.html"

spec = importlib.util.spec_from_file_location("poe_gpv", MODULE_PATH)
poe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poe)

html = FIXTURE.read_text(encoding="utf-8")
failures = []


def check(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


def runs(states, target):
    found = []
    start = None
    for index, state in enumerate(states):
        if state == target and start is None:
            start = index
        elif state != target and start is not None:
            found.append((start, index))
            start = None
    if start is not None:
        found.append((start, len(states)))
    return found


def label(index):
    return f"{index // 2:02d}:{30 if index % 2 else 0:02d}"


def windows(states, target):
    return [f"{label(start)}-{label(end)}" for start, end in runs(states, target)]


# --- one real day ---------------------------------------------------------
days = poe.parse_poe_page(html)
check("one day", sorted(days), [date(2026, 10, 20)])
check("twelve queues", len(days[date(2026, 10, 20)]), 12)

three_one = days[date(2026, 10, 20)]["3.1"]
check("48 slots", len(three_one), 48)
check("certain windows", windows(three_one, "off"), ["09:00-10:30", "15:00-15:30", "21:00-22:00"])
check(
    "possible windows",
    windows(three_one, "possible"),
    ["10:30-11:00", "15:30-16:00", "22:00-22:30"],
)
check("third state exists", sorted(set(three_one)), ["off", "on", "possible"])

# The other queues parse too, and every one has 48 cells.
for queue, states in days[date(2026, 10, 20)].items():
    if len(states) != 48:
        failures.append(f"queue {queue}: {len(states)} slots")

# --- two days on one page (the evening publication) -----------------------
second = html.replace("20 жовтня 2026", "21 жовтня 2026")
two_days = poe.parse_poe_page(html + second)
check("two days", sorted(two_days), [date(2026, 10, 20), date(2026, 10, 21)])
check("tomorrow has 3.1", "3.1" in two_days[date(2026, 10, 21)], True)

# --- a page without a table ----------------------------------------------
check("empty page", poe.parse_poe_page("<html><body>no schedule</body></html>"), {})

# --- the 2026-10-28 markup ------------------------------------------------
# The operator rebuilt the page on 2026-10-27 at 03:29 and renamed every class.
# The old classes (turnoff-scheduleui-table, light_N) are gone; the page now
# carries table.gpv-table and the state lives in gpv-s1/s2/s3. Without this
# branch the parser returns nothing and the integration keeps yesterday's day.
new_html = NEW_FIXTURE.read_text(encoding="utf-8")
new_days = poe.parse_poe_page(new_html)
check("new markup: one day", sorted(new_days), [date(2026, 10, 28)])
check("new markup: twelve queues", len(new_days[date(2026, 10, 28)]), 12)

new_three_one = new_days[date(2026, 10, 28)]["3.1"]
check("new markup: 48 slots", len(new_three_one), 48)
check(
    "new markup: certain windows",
    windows(new_three_one, "off"),
    ["06:00-06:30", "11:00-13:00", "17:00-19:30", "23:00-24:00"],
)
check(
    "new markup: possible windows",
    windows(new_three_one, "possible"),
    ["06:30-07:00", "13:00-13:30", "19:30-20:00"],
)
for queue, states in new_days[date(2026, 10, 28)].items():
    if len(states) != 48:
        failures.append(f"new markup queue {queue}: {len(states)} slots")

if failures:
    print("FAIL")
    for line in failures:
        print(" ", line)
    sys.exit(1)

print("ok - all poe_gpv tests passed")
