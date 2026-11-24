"""Outdoor temperature and humidity from another module's public event.
The clock (time.monotonic) is faked: nothing here depends on the real time."""
import asyncio
import math
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from mirrordash_weather import local_readings
from mirrordash_weather.local_readings import (
    FRESH_SECONDS,
    LocalReadings,
    parse_humidity,
    parse_temperature,
)
from mirrordash_weather.plugin import WeatherModule

TEMP_EVENT = "mirrordash_garage.outdoor_temperature"
HUMIDITY_EVENT = "mirrordash_garage.outdoor_humidity"
START = 1000.0  # an arbitrary fixed moment on the fake monotonic clock

PROVIDER_ANSWER = {"current": {"temperature_2m": 20.5, "wind_speed_10m": 4.5, "wind_direction_10m": 90,
                               "precipitation": 0.2, "weather_code": 1},
                   "daily": {"time": ["2026-06-03"], "weather_code": [1],
                             "temperature_2m_max": [21.0], "temperature_2m_min": [15.0]}}


class Answer(tuple):
    fetched_at = None


class FakeClock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(local_readings.time, "monotonic", fake)
    return fake


def make_module(bus=None, **settings):
    config = {"provider": "open_meteo", "event_bus": bus, "outdoor_temperature_event": TEMP_EVENT,
              "outdoor_humidity_event": HUMIDITY_EVENT, **settings}
    module = WeatherModule(config)
    module.fetch_json = AsyncMock(return_value=Answer((PROVIDER_ANSWER, None)))
    module.render_template = MagicMock(return_value="<div></div>")
    module.changed = MagicMock()
    return module


async def render_kwargs(module):
    await module.render()
    return module.render_template.call_args.kwargs


# --- Validation ---

@pytest.mark.parametrize("data", [
    {"value": True, "unit": "°C"}, {"value": False, "unit": "°C"},
    {"value": math.nan, "unit": "°C"}, {"value": math.inf, "unit": "°C"}, {"value": -math.inf, "unit": "°C"},
    {"value": "3.4", "unit": "°C"}, {"value": None, "unit": "°C"}, {"unit": "°C"},
    {"value": 3.4, "unit": "K"}, {"value": 3.4, "unit": "%"}, {"value": 3.4},
    {"value": 61, "unit": "°C"}, {"value": -91, "unit": "°C"},
    {"value": 141, "unit": "°F"},  # 60.6 °C
    "3.4", None, [3.4], 3.4,
])
def test_temperature_rejects_what_it_cannot_trust(data):
    assert parse_temperature(data) is None


def test_temperature_accepts_celsius_and_fahrenheit():
    assert parse_temperature({"value": 3.4, "unit": "°C"}) == 3.4
    assert parse_temperature({"value": 3, "unit": "C"}) == 3.0
    assert parse_temperature({"value": 68, "unit": "°F", "name": "Garden"}) == pytest.approx(20.0)  # other keys ignored
    assert parse_temperature({"value": 32, "unit": "F"}) == pytest.approx(0.0)
    assert parse_temperature({"value": 60, "unit": "°C"}) == 60.0 and parse_temperature({"value": -90, "unit": "°C"}) == -90.0


@pytest.mark.parametrize("data", [
    {"value": True, "unit": "%"}, {"value": math.nan, "unit": "%"}, {"value": math.inf, "unit": "%"},
    {"value": "82", "unit": "%"}, {"value": 82, "unit": "°C"}, {"value": 82, "unit": "percent"}, {"value": 82},
    {"value": -0.1, "unit": "%"}, {"value": 100.1, "unit": "%"}, "82", None,
])
def test_humidity_rejects_what_it_cannot_trust(data):
    assert parse_humidity(data) is None


def test_humidity_accepts_zero_to_hundred():
    assert parse_humidity({"value": 82, "unit": "%"}) == 82.0
    assert parse_humidity({"value": 0, "unit": "%"}) == 0.0
    assert parse_humidity({"value": 100, "unit": "%"}) == 100.0


# --- Fresh or stale ---

def test_a_reading_is_fresh_until_ten_minutes(clock):
    readings = LocalReadings()
    readings.store_temperature(3.4)
    readings.store_humidity(82.0)
    assert FRESH_SECONDS == 600
    clock.now = START + 599
    assert readings.fresh_temperature(clock.now) == 3.4 and readings.fresh_humidity(clock.now) == 82.0
    clock.now = START + 601
    assert readings.fresh_temperature(clock.now) is None and readings.fresh_humidity(clock.now) is None


def test_nothing_received_is_not_fresh(clock):
    assert LocalReadings().fresh_temperature(clock.now) is None


# --- Subscriptions ---

def test_subscribes_to_exactly_the_configured_names():
    bus = MagicMock()
    make_module(bus)
    assert sorted(call.args[0] for call in bus.subscribe.call_args_list) == [HUMIDITY_EVENT, TEMP_EVENT]


def test_only_the_set_name_is_subscribed():
    bus = MagicMock()
    make_module(bus, outdoor_humidity_event="")
    assert [call.args[0] for call in bus.subscribe.call_args_list] == [TEMP_EVENT]


def test_no_subscription_with_empty_settings_in_preview_or_without_a_bus():
    bus = MagicMock()
    make_module(bus, outdoor_temperature_event="", outdoor_humidity_event="")
    make_module(bus, preview=True)
    make_module(None)
    bus.subscribe.assert_not_called()


# --- Events in ---

@pytest.mark.asyncio
async def test_a_valid_reading_is_stored_and_redraws_at_once(clock):
    module = make_module(MagicMock())
    await module.on_outdoor_temperature({"value": 3.4, "unit": "°C"})
    module.changed.set.assert_called_once()
    assert module.local.fresh_temperature(clock.now) == 3.4
    module.stale_timer.cancel()


@pytest.mark.asyncio
async def test_an_invalid_reading_changes_nothing(clock):
    module = make_module(MagicMock())
    await module.on_outdoor_temperature({"value": True, "unit": "°C"})
    await module.on_outdoor_humidity({"value": 120, "unit": "%"})
    module.changed.set.assert_not_called()
    assert module.stale_timer is None


@pytest.mark.asyncio
async def test_a_reading_without_changed_attribute_is_fine(clock):
    module = make_module(MagicMock())
    del module.changed
    await module.on_outdoor_temperature({"value": 3.4, "unit": "°C"})
    module.stale_timer.cancel()


@pytest.mark.asyncio
async def test_one_redraw_is_planned_just_after_it_goes_stale_and_replaced_by_the_next(monkeypatch, clock):
    handles = []
    loop = asyncio.get_running_loop()

    def fake_call_later(delay, callback):
        handles.append((delay, callback, MagicMock()))
        return handles[-1][2]

    monkeypatch.setattr(loop, "call_later", fake_call_later)
    module = make_module(MagicMock())
    await module.on_outdoor_temperature({"value": 3.4, "unit": "°C"})
    await module.on_outdoor_humidity({"value": 80, "unit": "%"})
    assert [h[0] for h in handles] == [601, 601]
    handles[0][2].cancel.assert_called_once()  # the earlier timer was replaced
    handles[1][2].cancel.assert_not_called()
    module.changed.set.reset_mock()
    handles[1][1]()  # the timer fires
    module.changed.set.assert_called_once()


# --- Render ---

@pytest.mark.asyncio
async def test_a_fresh_local_temperature_replaces_the_providers(clock):
    module = make_module()
    module.local.store_temperature(3.44)
    kwargs = await render_kwargs(module)
    assert kwargs["weather"]["current"]["temp"] == 3.4
    assert kwargs["local_temp"] is True
    assert kwargs["local_humidity"] is None
    assert kwargs["weather"]["current"]["wind_speed"] == 4.5  # the rest stays the provider's


@pytest.mark.asyncio
async def test_a_stale_local_temperature_gives_the_providers_back(clock):
    module = make_module()
    module.local.store_temperature(3.4)
    clock.now = START + 601
    kwargs = await render_kwargs(module)
    assert kwargs["weather"]["current"]["temp"] == 20.5
    assert kwargs["local_temp"] is False


@pytest.mark.asyncio
async def test_without_any_reading_nothing_changes(clock):
    kwargs = await render_kwargs(make_module())
    assert kwargs["weather"]["current"]["temp"] == 20.5
    assert kwargs["local_temp"] is False and kwargs["local_humidity"] is None


@pytest.mark.asyncio
async def test_the_local_temperature_follows_the_mirrors_unit(clock):
    module = make_module(globals={"temperature_unit": "F"})
    module.local.store_temperature(20.0)
    kwargs = await render_kwargs(module)
    assert kwargs["weather"]["current"]["temp"] == 68.0
    assert kwargs["temp_unit_label"] == "°F"


@pytest.mark.asyncio
async def test_a_fresh_humidity_is_passed_rounded_and_goes_stale(clock):
    module = make_module()
    module.local.store_humidity(81.6)
    assert (await render_kwargs(module))["local_humidity"] == 82
    clock.now = START + 599
    assert (await render_kwargs(module))["local_humidity"] == 82
    clock.now = START + 601
    assert (await render_kwargs(module))["local_humidity"] is None


@pytest.mark.asyncio
async def test_a_weather_error_is_left_alone(clock):
    module = make_module()
    module.fetch_json = AsyncMock(return_value=Answer((None, "rejected")))
    module.local.store_temperature(3.4)
    module.local.store_humidity(80.0)
    kwargs = await render_kwargs(module)
    assert "error" in kwargs["weather"] and "current" not in kwargs["weather"]
    assert kwargs["local_temp"] is False and kwargs["local_humidity"] is None


@pytest.mark.asyncio
async def test_rendering_asks_the_provider_through_fetch_json_so_a_young_answer_is_reused(clock):
    # No extra API call per reading: render only calls fetch_json, which reuses a young answer
    module = make_module()
    module.local.store_temperature(3.4)
    await module.render()
    module.fetch_json.assert_awaited_once()


# --- Template ---

TEMPLATE = (Path(__file__).parents[1] / "mirrordash_weather/templates/widget.html").read_text()


def test_template_marks_the_local_temperature_and_adds_the_humidity_row():
    assert "{% if local_temp %}" in TEMPLATE
    assert 'data-lucide="house" class="local-mark"' in TEMPLATE
    assert 'data-lucide="droplets" class="detail-icon"' in TEMPLATE
    assert "{{ local_humidity }} %" in TEMPLATE
    assert "local_humidity is not none or" in TEMPLATE  # the details block shows with only humidity
    assert "margin: 6px 0 0 6px" in TEMPLATE and ".detail-item .local-mark" in TEMPLATE


def test_the_house_icon_title_is_translated():
    import json
    for lang, text in (("en", "Own sensor"), ("sv", "Egen sensor")):
        translations = json.loads((Path(__file__).parents[1] / f"mirrordash_weather/translations/{lang}.json").read_text())
        assert translations["own_sensor"] == text
