import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from mirrordash_weather.plugin import SMHI_WARNINGS_URL, WeatherModule, in_area


class Answer(tuple):
    """What the mirror's fetch_json gives: (data, error), and .fetched_at, when the data was downloaded."""
    fetched_at = datetime.datetime(2026, 1, 1, 9, 30)

MOCK_SMHI_DATA = {
    "referenceTime": "2026-06-03T18:00:00Z",
    # Real SMHI API uses 'timeSeries', with 'time' and 'data' dict
    "timeSeries": [
        {
            "time": "2026-06-03T19:00:00Z",
            "data": {
                "air_temperature": 20.5,
                "wind_speed": 4.5,
                "wind_from_direction": 90.0,
                "symbol_code": 2,
                "precipitation_amount_mean": 0.2
            }
        },
        {
            "time": "2026-06-04T12:00:00Z",
            "data": {
                "air_temperature": 22.0,
                "wind_speed": 5.0,
                "wind_from_direction": 95.0,
                "symbol_code": 1,
                "precipitation_amount_mean": 0.0
            }
        }
    ]
}

MOCK_OPEN_METEO_DATA = {
    "current": {
        "temperature_2m": 20.5,
        "wind_speed_10m": 4.5,
        "wind_direction_10m": 90,
        "precipitation": 0.2,
        "weather_code": 1
    },
    "daily": {
        "time": ["2026-06-03", "2026-06-04"],
        "weather_code": [1, 0],
        "temperature_2m_max": [21.0, 23.0],
        "temperature_2m_min": [15.0, 16.0]
    }
}

MOCK_WEATHERAPI_DATA = {
    "current": {
        "temp_c": 20.5,
        "wind_kph": 16.2,  # 16.2 / 3.6 = 4.5 m/s
        "wind_degree": 90,
        "precip_mm": 0.2,
        "condition": {
            "code": 1003
        }
    },
    "forecast": {
        "forecastday": [
            {
                "date": "2026-06-03",
                "day": {
                    "maxtemp_c": 21.0,
                    "mintemp_c": 15.0,
                    "condition": {
                        "code": 1003
                    }
                }
            },
            {
                "date": "2026-06-04",
                "day": {
                    "maxtemp_c": 23.0,
                    "mintemp_c": 16.0,
                    "condition": {
                        "code": 1000
                    }
                }
            }
        ]
    }
}

MOCK_OPENWEATHER_DATA = {
    "list": [
        {
            "dt": 1780513200,  # 2026-06-03 19:00:00
            "main": {
                "temp": 20.5,
                "temp_min": 15.0,
                "temp_max": 21.0
            },
            "wind": {
                "speed": 4.5,
                "deg": 90
            },
            "rain": {
                "3h": 0.2
            },
            "weather": [
                {
                    "id": 801
                }
            ]
        },
        {
            "dt": 1780574400,  # 2026-06-04 12:00:00
            "main": {
                "temp": 22.0,
                "temp_min": 16.0,
                "temp_max": 23.0
            },
            "wind": {
                "speed": 5.0,
                "deg": 95
            },
            "weather": [
                {
                    "id": 800
                }
            ]
        }
    ]
}

@pytest.fixture
def base_config():
    return {
        "globals": {
            "language": "en",
            "timezone": "Europe/Stockholm",
            "time_format": "24h",
            "temperature_unit": "C",
            "distance_unit": "km",
            "latitude": 59.3293,
            "longitude": 18.0686
        },
        "provider": "smhi",
        "show_header": True,
        "show_wind": True,
        "show_precipitation": True,
        "show_forecast": True,
        "forecast_days": 4
    }

def test_weather_module_init_and_fallbacks(base_config):
    # Test fallback to globals
    module = WeatherModule(base_config)
    assert module.latitude == 59.3293
    assert module.longitude == 18.0686
    assert module.temp_unit == "C"
    assert module.dist_unit == "km"
    assert module.tz == ZoneInfo("Europe/Stockholm")
    
    # Test fallback to hardcoded default if globals are missing
    empty_config = {"globals": {}}
    module_default = WeatherModule(empty_config)
    assert module_default.latitude == 59.3293
    assert module_default.longitude == 18.0686
    assert module_default.tz == ZoneInfo("Europe/Stockholm")

def test_weather_module_unit_conversions(base_config):
    module = WeatherModule(base_config)
    
    # Celsius to Celsius (no conversion)
    assert module.convert_temp(20.5) == 20.5
    
    # Celsius to Fahrenheit conversion
    module.temp_unit = "F"
    assert module.convert_temp(20.0) == 68.0
    assert module.convert_temp(0.0) == 32.0
    
    # Wind speed conversion (m/s to m/s)
    module.dist_unit = "km"
    assert module.convert_wind_speed(5.0) == 5.0
    
    # Wind speed conversion (m/s to mph)
    module.dist_unit = "miles"
    assert module.convert_wind_speed(5.0) == 11.2  # 5 * 2.23694 = 11.1847

def test_parse_smhi(base_config):
    module = WeatherModule(base_config)
    today = datetime.date(2026, 6, 3)
    
    result = module.parse_smhi(MOCK_SMHI_DATA, today)
    assert result["current"]["temp"] == 20.5
    assert result["current"]["icon"] == "cloud-sun"
    assert result["current"]["condition"] == "Partly Cloudy"
    assert result["current"]["wind_speed"] == 4.5
    assert result["current"]["wind_dir"] == "E"  # 90 degrees
    assert result["current"]["precipitation"] == 0.2
    
    assert len(result["forecast"]) == 1
    assert result["forecast"][0]["day_name"] == "TOMORROW"
    assert result["forecast"][0]["temp_max"] == 22.0
    assert result["forecast"][0]["icon"] == "sun"

def test_parse_open_meteo(base_config):
    base_config["provider"] = "open_meteo"
    module = WeatherModule(base_config)
    today = datetime.date(2026, 6, 3)
    
    result = module.parse_open_meteo(MOCK_OPEN_METEO_DATA, today)
    assert result["current"]["temp"] == 20.5
    assert result["current"]["icon"] == "cloud-sun"
    assert result["current"]["wind_speed"] == 4.5
    assert result["current"]["wind_dir"] == "E"
    assert result["current"]["precipitation"] == 0.2
    
    assert len(result["forecast"]) == 1
    assert result["forecast"][0]["day_name"] == "TOMORROW"
    assert result["forecast"][0]["temp_max"] == 23.0
    assert result["forecast"][0]["temp_min"] == 16.0
    assert result["forecast"][0]["icon"] == "sun"

def test_parse_weatherapi(base_config):
    base_config["provider"] = "weatherapi"
    module = WeatherModule(base_config)
    today = datetime.date(2026, 6, 3)
    
    result = module.parse_weatherapi(MOCK_WEATHERAPI_DATA, today)
    assert result["current"]["temp"] == 20.5
    assert result["current"]["icon"] == "cloud-sun"
    assert result["current"]["wind_speed"] == 4.5  # converted from 16.2 kph
    assert result["current"]["wind_dir"] == "E"
    assert result["current"]["precipitation"] == 0.2
    
    assert len(result["forecast"]) == 1
    assert result["forecast"][0]["day_name"] == "TOMORROW"
    assert result["forecast"][0]["temp_max"] == 23.0
    assert result["forecast"][0]["icon"] == "sun"

def test_parse_openweathermap(base_config):
    base_config["provider"] = "openweathermap"
    module = WeatherModule(base_config)
    
    # Mock timezone to UTC to match openweather timestamps in Europe/Stockholm (+2 in June)
    # 1780513200 is June 3, 2026 19:00:00 Stockholm local time
    # Let's set module timezone to stockholm and mock today as June 3, 2026
    today = datetime.date(2026, 6, 3)
    
    result = module.parse_openweathermap(MOCK_OPENWEATHER_DATA, today)
    assert result["current"]["temp"] == 20.5
    assert result["current"]["icon"] == "cloud-sun"
    assert result["current"]["wind_speed"] == 4.5
    assert result["current"]["wind_dir"] == "E"
    assert result["current"]["precipitation"] == 0.2
    
    assert len(result["forecast"]) == 1
    assert result["forecast"][0]["day_name"] == "TOMORROW"
    assert result["forecast"][0]["temp_max"] == 23.0
    assert result["forecast"][0]["icon"] == "sun"

def test_parse_hourly_and_combined(base_config):
    # SMHI Hourly Parsing
    module = WeatherModule(base_config)
    today = datetime.date(2026, 6, 3)
    result = module.parse_smhi(MOCK_SMHI_DATA, today)
    assert "hourly_forecast" in result
    assert len(result["hourly_forecast"]) > 0
    assert result["hourly_forecast"][0]["time_label"] == "21:00" or result["hourly_forecast"][0]["time_label"] == "09 PM"
    assert result["hourly_forecast"][0]["temp"] == 20.5

    # Open-Meteo Hourly Parsing
    base_config["provider"] = "open_meteo"
    om_module = WeatherModule(base_config)
    om_data = MOCK_OPEN_METEO_DATA.copy()
    om_data["hourly"] = {
        "time": ["2026-06-03T19:00", "2026-06-03T20:00"],
        "temperature_2m": [20.5, 19.5],
        "weather_code": [1, 1]
    }
    om_result = om_module.parse_open_meteo(om_data, today)
    assert len(om_result["hourly_forecast"]) == 2
    assert om_result["hourly_forecast"][0]["time_label"] == "19:00"
    assert om_result["hourly_forecast"][0]["temp"] == 20.5

    # WeatherAPI Hourly Parsing
    base_config["provider"] = "weatherapi"
    wa_module = WeatherModule(base_config)
    wa_data = MOCK_WEATHERAPI_DATA.copy()
    wa_data["forecast"] = {
        "forecastday": [
            {
                "date": "2026-06-03",
                "day": {"maxtemp_c": 21.0, "mintemp_c": 15.0, "condition": {"code": 1003}},
                "hour": [
                    {"time": "2026-06-03 19:00", "temp_c": 20.5, "condition": {"code": 1003}}
                ]
            }
        ]
    }
    wa_result = wa_module.parse_weatherapi(wa_data, today)
    assert len(wa_result["hourly_forecast"]) == 1
    assert wa_result["hourly_forecast"][0]["time_label"] == "19:00"
    assert wa_result["hourly_forecast"][0]["temp"] == 20.5

    # OpenWeatherMap Hourly Parsing
    base_config["provider"] = "openweathermap"
    owm_module = WeatherModule(base_config)
    owm_result = owm_module.parse_openweathermap(MOCK_OPENWEATHER_DATA, today)
    assert len(owm_result["hourly_forecast"]) > 0
    assert owm_result["hourly_forecast"][0]["temp"] == 20.5


@pytest.mark.asyncio
async def test_api_key_goes_in_params_and_a_rejected_key_says_so():
    module = WeatherModule({"provider": "weatherapi", "weatherapi_key": "secret-key"})
    module.fetch_json = AsyncMock(return_value=Answer((None, "rejected")))
    module.render_template = MagicMock(return_value="<div></div>")
    await module.render()
    url = module.fetch_json.await_args.args[0]
    assert "secret-key" not in url  # the key is never part of an address that could be logged
    assert module.fetch_json.await_args.kwargs["params"]["key"] == "secret-key"
    assert "rejected" in module.render_template.call_args.kwargs["weather"]["error"]



def test_no_never_ending_animation():
    # A never-ending CSS animation redraws the screen 60 times a second and keeps the Pi warm: the mirror stands still
    assert "infinite" not in (Path(__file__).parents[1] / "mirrordash_weather/templates/widget.html").read_text()


@pytest.mark.asyncio
async def test_last_checked_is_when_the_data_was_downloaded():
    module = WeatherModule({"provider": "open_meteo"})
    module.fetch_json = AsyncMock(return_value=Answer((MOCK_OPEN_METEO_DATA, None)))
    module.render_template = MagicMock(return_value="<div></div>")
    await module.render()
    assert module.render_template.call_args.kwargs["last_checked"] == "09:30"  # not the time of drawing


# --- Weather warnings ---

STOCKHOLM = [[17.5, 59.0], [18.5, 59.0], [18.5, 59.6], [17.5, 59.6], [17.5, 59.0]]
LAPLAND = [[15.0, 66.0], [20.0, 66.0], [20.0, 69.0], [15.0, 69.0], [15.0, 66.0]]
NOW = datetime.datetime(2026, 11, 4, 14, 0, tzinfo=ZoneInfo("Europe/Stockholm"))


def smhi_warning(code, level_sv, title, ring, start, end=None):
    area = {"warningLevel": {"sv": level_sv, "en": level_sv, "code": code}, "eventDescription": {"sv": title, "en": title},
            "approximateStart": start, "area": {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}}}
    if end:
        area["approximateEnd"] = end
    return {"event": {"sv": title, "en": title}, "warningAreas": [area]}


SMHI_WARNINGS = [
    smhi_warning("MESSAGE", "Meddelande", "Risk för vattenbrist", STOCKHOLM, "2026-05-04T22:00:00.000Z"),
    smhi_warning("YELLOW", "Gul", "Vind", STOCKHOLM, "2026-11-04T17:00:00.000Z", "2026-11-05T05:00:00.000Z"),
    smhi_warning("ORANGE", "Orange", "Vind på kalfjället", LAPLAND, "2026-11-04T11:00:00.000Z", "2026-11-05T05:00:00.000Z"),
    smhi_warning("RED", "Röd", "Gammal storm", STOCKHOLM, "2026-11-01T00:00:00.000Z", "2026-11-02T00:00:00.000Z"),
]


def test_in_area_polygons_holes_and_multipolygons():
    square = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    hole = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]
    assert in_area(2, 2, {"type": "Polygon", "coordinates": [square]})
    assert not in_area(12, 2, {"type": "Polygon", "coordinates": [square]})
    assert not in_area(5, 5, {"type": "Polygon", "coordinates": [square, hole]})  # in the hole
    assert in_area(5, 5, {"type": "MultiPolygon", "coordinates": [[hole], [square]]})
    assert not in_area(5, 5, None)


def test_smhi_warnings_for_the_mirrors_place_only(base_config):
    module = WeatherModule({**base_config, "globals": {**base_config["globals"], "language": "sv"}})
    module.translations = {"warning_level": "{level} varning", "today": "Idag", "tomorrow": "Imorgon",
                           "warning_until_further_notice": "Tills vidare"}
    warnings = module.parse_smhi_warnings(SMHI_WARNINGS, NOW)
    # Not Lapland's (another place), not the storm that is over, not the message (hidden by default)
    assert [(w["level"], w["title"], w["when"]) for w in warnings] == [("Gul varning", "Vind", "Idag 18:00 – imorgon 06:00")]

    module.warnings = "all"
    message = module.parse_smhi_warnings(SMHI_WARNINGS, NOW)[0]
    assert (message["level"], message["message"], message["when"]) == ("Meddelande", True, "Tills vidare")


def test_warning_when(base_config):
    module = WeatherModule(base_config)
    at = lambda hour, day=4: datetime.datetime(2026, 11, day, hour, tzinfo=ZoneInfo("Europe/Stockholm"))
    assert module.warning_when(at(18), at(6, 5), NOW) == "Today 18:00 – tomorrow 06:00"
    assert module.warning_when(at(9), at(6, 5), NOW) == "Until tomorrow 06:00"  # already begun
    assert module.warning_when(at(18), None, NOW) == "From today 18:00"
    assert module.warning_when(at(9, 1), None, NOW) == "Until further notice"
    assert module.warning_when(at(9, 6), None, NOW).startswith("From fri")


@pytest.mark.asyncio
async def test_warnings_most_severe_first_and_off_fetches_nothing(base_config):
    module = WeatherModule(base_config)
    module.fetch_json = AsyncMock(return_value=Answer((SMHI_WARNINGS + [smhi_warning(
        "ORANGE", "Orange", "Snöfall", STOCKHOLM, "2026-11-04T10:00:00.000Z")], None)))
    warnings = await module.fetch_warnings(None, NOW)
    module.fetch_json.assert_awaited_once_with(SMHI_WARNINGS_URL)
    assert [w["title"] for w in warnings] == ["Snöfall", "Vind"]

    module.warnings = "off"
    module.fetch_json.reset_mock()
    assert await module.fetch_warnings(None, NOW) == []
    module.fetch_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_weatherapi_alerts_once_each(base_config):
    module = WeatherModule({**base_config, "provider": "weatherapi"})
    alert = {"event": "Moderate wind warning", "severity": "Moderate",
             "effective": "2026-11-04T16:00:00+00:00", "expires": "2026-11-05T05:00:00+00:00"}
    data = {"alerts": {"alert": [alert, alert, {**alert, "event": "Minor fog", "severity": "Minor"},
                                 {**alert, "event": "Old", "expires": "2026-11-01T00:00:00+00:00"}]}}
    found = await module.fetch_warnings(data, NOW)
    assert [w["title"] for w in found] == ["Moderate wind warning"]  # once, not the copy, the minor or the old one
    assert found[0]["level"] == "Warning" and found[0]["when"] == "Today 17:00 – tomorrow 06:00"
