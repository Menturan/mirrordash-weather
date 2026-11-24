"""Outdoor readings from the owner's own sensor, sent by another module as a public event.

The payload is the shared "reading" shape: {"value": <number>, "unit": <text>}. It comes from
another module, so it is untrusted: every check below is there to drop what we can't use."""
import math
import time

FRESH_SECONDS = 600  # an older reading is stale: the provider's temperature comes back

TEMPERATURE_RANGE_C = (-90.0, 60.0)  # beyond this a sensor is broken, not the weather
HUMIDITY_RANGE = (0.0, 100.0)


def read_number(data) -> float | None:
    """The reading's value if it is a real, finite number. bool is an int in Python, so it is refused by hand."""
    if not isinstance(data, dict):
        return None
    value = data.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def parse_temperature(data) -> float | None:
    """The temperature in °C, or None when the reading can't be used."""
    value = read_number(data)
    if value is None:
        return None
    unit = data.get("unit")
    if unit in ("°C", "C"):
        celsius = value
    elif unit in ("°F", "F"):
        celsius = (value - 32.0) * 5.0 / 9.0
    else:
        return None
    low, high = TEMPERATURE_RANGE_C
    return celsius if low <= celsius <= high else None


def parse_humidity(data) -> float | None:
    """The relative humidity in percent, or None when the reading can't be used."""
    value = read_number(data)
    if value is None or data.get("unit") != "%":
        return None
    low, high = HUMIDITY_RANGE
    return value if low <= value <= high else None


def now() -> float:
    return time.monotonic()


def is_fresh(stamp: float | None, now: float) -> bool:
    return stamp is not None and now - stamp < FRESH_SECONDS


class LocalReadings:
    """The last good temperature and humidity, each with the moment (time.monotonic) it arrived."""

    def __init__(self):
        self.temperature_c: float | None = None
        self.temperature_at: float | None = None
        self.humidity: float | None = None
        self.humidity_at: float | None = None

    def store_temperature(self, celsius: float) -> None:
        self.temperature_c, self.temperature_at = celsius, now()

    def store_humidity(self, percent: float) -> None:
        self.humidity, self.humidity_at = percent, now()

    def fresh_temperature(self, now: float) -> float | None:
        return self.temperature_c if is_fresh(self.temperature_at, now) else None

    def fresh_humidity(self, now: float) -> float | None:
        return self.humidity if is_fresh(self.humidity_at, now) else None
