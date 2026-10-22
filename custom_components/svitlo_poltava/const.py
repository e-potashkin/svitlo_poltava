"""Constants for Svitlo Poltava."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "svitlo_poltava"

# The queue is chosen in the config flow. 3.1 is Eugene's queue and the default.
DEFAULT_QUEUE = "3.1"
REGION = "Poltava"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
]

VERSION = "1.0.1"
DEFAULT_SCAN_INTERVAL = 120
CONF_QUEUE = "queue"
CONF_SCAN_INTERVAL = "scan_interval_seconds"

# The official schedule of Poltavaoblenergo. One page carries today and, in the
# evening, tomorrow. This is the only source the component reads.
POE_GPV_URL = "https://www.poe.pl.ua/customs/dynamicgpv-info.php"

# The card is served from the component itself, so a HACS install carries it.
CARD_URL = "/svitlo_poltava_static/svitlo-poltava-card.js"
CARD_STATIC_PATH = "/svitlo_poltava_static"
