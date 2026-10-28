"""Official Poltavaoblenergo schedule — the only source for Poltava.

The home page fills `<div class="dynamic-loaded-gpv">` from
https://www.poe.pl.ua/customs/dynamicgpv-info.php . The response is one or more
`div.gpvinfodetail` blocks, each with its own date and a table of 48 half-hour
cells per queue:

    light_1  power on
    light_2  outage
    light_3  possible outage

In the evening the operator adds the next day to the same response, so the page
can carry today and tomorrow at once. Each block is parsed with its own date, so
the coordinator can pick the day it needs.

The page is the only source this integration reads for Poltava: no proxies, no
merge, no estimates.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

POE_GPV_URL = "https://www.poe.pl.ua/customs/dynamicgpv-info.php"

STATE_ON = "on"
STATE_OFF = "off"
STATE_POSSIBLE = "possible"

_BLOCK_RE = re.compile(r'<div[^>]*class="[^"]*gpvinfodetail[^"]*"')
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_QUEUE_RE = re.compile(r'turnoff-scheduleui-table-queue"[^>]*>([^<]+)<')
_SUB_RE = re.compile(r'turnoff-scheduleui-table-subqueue"[^>]*>([^<]+)<')
_CELL_RE = re.compile(r'class="(light_\d+)"')
_TABLE_RE = re.compile(r'<table[^>]*turnoff-scheduleui-table')

_DATE_RE = re.compile(r"(\d{1,2})\s+([А-Яа-яІіЇїЄєҐґ]+)\s+(\d{4})")
_MONTHS = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5, "червня": 6,
    "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12,
}

_CELL_STATES = {"light_1": STATE_ON, "light_2": STATE_OFF, "light_3": STATE_POSSIBLE}

# 2026-10-28 markup. The operator rebuilt the page on 2026-10-27 at 03:29 and
# renamed every class, so the old regexes below stopped matching:
#
#   <table class="gpv-table">
#   <tr class="gpv-first"><td class="gpv-q" title="Черга 1, підчерга 1">1.1</td>
#   <td class="gpv-c gpv-s1 gpv-h gpv-past" title="1.1: 00:00–00:30 — «Увімкнено»...">
#
# s1 = on, s2 = off, s3 = possible (the switching time). The clock is not a
# cell: the header carries the hours and <tr class="gpv-mm"> carries 00/30.
_TABLE_NEW_RE = re.compile(r'<table[^>]*class="[^"]*\bgpv-table\b[^"]*"')
_QUEUE_NEW_RE = re.compile(r'<td[^>]*class="[^"]*\bgpv-q\b[^"]*"[^>]*>\s*(\d+\.\d+)\s*</td>')
_CELL_NEW_RE = re.compile(r'<td[^>]*class="([^"]*\bgpv-c\b[^"]*)"')
_S_CLASS_RE = re.compile(r"\bgpv-s(\d)\b")
_NEW_STATES = {"1": STATE_ON, "2": STATE_OFF, "3": STATE_POSSIBLE}


def _parse_new_queues(block: str) -> dict[str, list[str]]:
    """The 2026-10-28 table, one 48-cell row per queue."""
    if not _TABLE_NEW_RE.search(block):
        return {}
    queues: dict[str, list[str]] = {}
    for row in _ROW_RE.findall(block):
        queue_cell = _QUEUE_NEW_RE.search(row)
        if not queue_cell:
            continue
        cells = _CELL_NEW_RE.findall(row)
        if len(cells) != 48:
            continue
        states: list[str] = []
        for cell in cells:
            match = _S_CLASS_RE.search(cell)
            state = _NEW_STATES.get(match.group(1)) if match else None
            if state is None:
                states = []
                break
            states.append(state)
        if states:
            queues[queue_cell.group(1)] = states
    return queues


def _blocks(html: str) -> list[str]:
    """Split the response into per-day blocks."""
    starts = [match.start() for match in _BLOCK_RE.finditer(html)]
    if not starts:
        has_table = _TABLE_RE.search(html) or _TABLE_NEW_RE.search(html)
        return [html] if has_table else []
    return [
        html[start : (starts[index + 1] if index + 1 < len(starts) else len(html))]
        for index, start in enumerate(starts)
    ]


def parse_block_date(block: str) -> Optional[date]:
    """The date printed in the block header."""
    for day, month, year in _DATE_RE.findall(block):
        month_number = _MONTHS.get(month.lower())
        if month_number is None:
            continue
        try:
            return date(int(year), month_number, int(day))
        except ValueError:
            return None
    return None


def parse_block_queues(block: str) -> dict[str, list[str]]:
    """The 48-cell row of every queue in one block."""
    queues = _parse_new_queues(block)
    if queues:
        return queues
    current: Optional[str] = None
    for row in _ROW_RE.findall(block):
        queue_cell = _QUEUE_RE.search(row)
        if queue_cell:
            current = queue_cell.group(1)
        sub_cell = _SUB_RE.search(row)
        cells = _CELL_RE.findall(row)
        if not sub_cell or len(cells) != 48 or not current:
            continue
        number = re.search(r"\d+", current)
        if not number:
            continue
        key = f"{number.group(0)}.{sub_cell.group(1).strip()}"
        queues[key] = [_CELL_STATES.get(cell, STATE_ON) for cell in cells]
    return queues


def parse_poe_page(html: str) -> dict[date, dict[str, list[str]]]:
    """Every day the page carries, keyed by date."""
    days: dict[date, dict[str, list[str]]] = {}
    for block in _blocks(html):
        day = parse_block_date(block)
        queues = parse_block_queues(block)
        if day and queues:
            days[day] = queues
    return days
