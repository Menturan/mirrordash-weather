# Licensed under the PolyForm Noncommercial License 1.0.0.

import asyncio
import logging
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from babel.dates import format_date as babel_format_date

logger = logging.getLogger("mirrordash.modules.mirrordash_weather")

UNIFIED_ICONS = {
    "clear": "sun",
    "partly_cloudy": "cloud-sun",
    "cloudy": "cloud",
    "overcast": "cloud",
    "fog": "cloud-fog",
    "drizzle": "cloud-drizzle",
    "rain": "cloud-rain",
    "heavy_rain": "cloud-rain",
    "snow": "cloud-snow",
    "sleet": "cloud-hail",
    "thunderstorm": "cloud-lightning"
}

SMHI_CONDITION_MAP = {
    1: "clear",
    2: "partly_cloudy",
    3: "partly_cloudy",
    4: "partly_cloudy",
    5: "cloudy",
    6: "overcast",
    7: "fog",
    8: "drizzle",
    9: "rain",
    10: "heavy_rain",
    11: "thunderstorm",
    12: "sleet",
    13: "sleet",
    14: "sleet",
    15: "snow",
    16: "snow",
    17: "snow",
    18: "drizzle",
    19: "rain",
    20: "heavy_rain",
    21: "thunderstorm",
    22: "sleet",
    23: "sleet",
    24: "sleet",
    25: "snow",
    26: "snow",
    27: "snow"
}

WMO_CONDITION_MAP = {
    0: "clear",
    1: "partly_cloudy",
    2: "partly_cloudy",
    3: "overcast",
    45: "fog",
    48: "fog",
    51: "drizzle",
    53: "drizzle",
    55: "drizzle",
    56: "sleet",
    57: "sleet",
    61: "rain",
    63: "rain",
    65: "heavy_rain",
    66: "sleet",
    67: "sleet",
    71: "snow",
    73: "snow",
    75: "snow",
    77: "snow",
    80: "drizzle",
    81: "rain",
    82: "heavy_rain",
    85: "snow",
    86: "snow",
    95: "thunderstorm",
    96: "thunderstorm",
    99: "thunderstorm"
}

WEATHERAPI_CONDITION_MAP = {
    1000: "clear",
    1003: "partly_cloudy",
    1006: "cloudy",
    1009: "overcast",
    1030: "fog",
    1063: "drizzle",
    1066: "snow",
    1069: "sleet",
    1072: "sleet",
    1087: "thunderstorm",
    1114: "snow",
    1117: "snow",
    1135: "fog",
    1147: "fog",
    1150: "drizzle",
    1153: "drizzle",
    1168: "sleet",
    1171: "sleet",
    1180: "drizzle",
    1183: "drizzle",
    1186: "rain",
    1189: "rain",
    1192: "heavy_rain",
    1195: "heavy_rain",
    1198: "sleet",
    1201: "sleet",
    1204: "sleet",
    1207: "sleet",
    1210: "snow",
    1213: "snow",
    1216: "snow",
    1219: "snow",
    1222: "snow",
    1225: "snow",
    1237: "snow",
    1240: "drizzle",
    1243: "rain",
    1246: "heavy_rain",
    1249: "sleet",
    1252: "sleet",
    1255: "snow",
    1258: "snow",
    1261: "snow",
    1264: "snow",
    1273: "thunderstorm",
    1276: "thunderstorm",
    1279: "thunderstorm",
    1282: "thunderstorm"
}

def map_openweathermap_code(code: int) -> str:
    if 200 <= code <= 232:
        return "thunderstorm"
    elif 300 <= code <= 321:
        return "drizzle"
    elif 500 <= code <= 531:
        return "rain"
    elif 600 <= code <= 622:
        return "snow"
    elif 701 <= code <= 781:
        return "fog"
    elif code == 800:
        return "clear"
    elif code in (801, 802):
        return "partly_cloudy"
    elif code == 803:
        return "cloudy"
    elif code == 804:
        return "overcast"
    return "clear"

def get_wind_direction_cardinal(deg: float) -> str:
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = int((deg + 11.25) / 22.5) % 16
    return directions[idx]

class WeatherModule:
    def __init__(self, config):
        self.config = config
        self.name = "mirrordash_weather"
        self.interval = config.get("interval", 900)
        
        self.last_error = None  # fetch_json's error from the last update, e.g. "rejected"

        # Translations
        self.translations = config.get("translations", {})
        
        # Event Bus
        self.event_bus = config.get("event_bus")
        
        # Resolve config & globals
        global_cfg = config.get("globals", {})
        self.lang = global_cfg.get("language", "en")
        
        self.latitude = config.get("latitude") or global_cfg.get("latitude", 59.3293)
        self.longitude = config.get("longitude") or global_cfg.get("longitude", 18.0686)
        
        self.provider = config.get("provider", "smhi")
        self.weatherapi_key = config.get("weatherapi_key", "")
        self.openweathermap_key = config.get("openweathermap_key", "")
        
        self.show_header = config.get("show_header", True)
        self.show_wind = config.get("show_wind", True)
        self.show_precipitation = config.get("show_precipitation", True)
        self.show_forecast = config.get("show_forecast", True)
        self.forecast_days = config.get("forecast_days", 4)
        self.forecast_type = config.get("forecast_type", "daily")
        self.layout = config.get("layout", "horizontal")
        self.forecast_hours = config.get("forecast_hours", 6)
        
        self.temp_unit = global_cfg.get("temperature_unit", "C")
        self.dist_unit = global_cfg.get("distance_unit", "km")
        self.time_format = global_cfg.get("time_format", "24h")
        
        timezone_name = global_cfg.get("timezone", "Europe/Stockholm")
        try:
            self.tz = ZoneInfo(timezone_name)
        except Exception:
            self.tz = ZoneInfo("UTC")
            
        logger.info(
            f"Initializing WeatherModule: provider={self.provider}, lat={self.latitude}, "
            f"lon={self.longitude}, tz={timezone_name}, lang={self.lang}, units={self.temp_unit}/{self.dist_unit}"
        )

    def translate(self, key: str, default: str = None) -> str:
        if not hasattr(self, "translations") or not self.translations:
            return default if default is not None else key
        val = self.translations.get(key)
        if val is not None:
            return val
        return default if default is not None else key

    def convert_temp(self, temp_c: float) -> float:
        if self.temp_unit == "F":
            return round(temp_c * 9.0 / 5.0 + 32.0, 1)
        return round(temp_c, 1)

    def convert_wind_speed(self, speed_ms: float) -> float:
        if self.dist_unit == "miles":
            return round(speed_ms * 2.23694, 1)
        return round(speed_ms, 1)

    def get_temp_unit_label(self) -> str:
        return "°F" if self.temp_unit == "F" else "°C"

    def get_wind_unit_label(self) -> str:
        return "mph" if self.dist_unit == "miles" else "m/s"

    async def fetch_api(self, url: str, params: dict | None = None) -> dict:
        """The provider's answer, or the last good one when it can't be reached (fetch_json keeps it,
        also over a restart). API keys go in params: fetch_json never logs the query."""
        data, self.last_error = await self.fetch_json(url, params=params)
        return data or {}

    def get_hour_label(self, dt: datetime) -> str:
        if self.time_format == "12h":
            return dt.strftime("%I %p").lstrip('0')
        else:
            return dt.strftime("%H:%M")

    def get_day_label(self, d: date, today_date: date) -> str:
        diff_days = (d - today_date).days
        if diff_days == 0:
            return self.translate("today", "Today").upper()
        elif diff_days == 1:
            return self.translate("tomorrow", "Tomorrow").upper()
        
        try:
            formatted = babel_format_date(d, format="EEE", locale=self.lang)
            return formatted.upper()
        except Exception:
            return d.strftime("%a").upper()

    def parse_smhi(self, data: dict, today_date: date) -> dict:
        if not data or "timeSeries" not in data:
            logger.warning("SMHI response missing 'timeSeries' key. Keys present: %s", list(data.keys()) if data else [])
            return {}

        timeseries = data["timeSeries"]
        if not timeseries:
            return {}

        # Resolve now_dt and today_val for relative date/time calculations
        if isinstance(today_date, datetime):
            now_dt = today_date
            today_val = today_date.date()
        else:
            now_dt = datetime.combine(today_date, time.min, tzinfo=self.tz)
            today_val = today_date

        # Use the first (soonest) entry as current conditions
        current_entry = timeseries[0]
        entry_data = current_entry.get("data", {})

        curr_temp    = entry_data.get("air_temperature", 0.0)
        curr_wind    = entry_data.get("wind_speed", 0.0)
        curr_wind_deg = entry_data.get("wind_from_direction", 0.0)
        curr_precip  = entry_data.get("precipitation_amount_mean", 0.0)
        curr_sym     = int(entry_data.get("symbol_code", 1))

        cond_key = SMHI_CONDITION_MAP.get(curr_sym, "clear")

        # Build daily forecast groups (future days only)
        daily_groups: dict = {}
        hourly_forecast = []

        for entry in timeseries:
            time_str = entry.get("time", "")
            if not time_str:
                continue
            try:
                dt = datetime.fromisoformat(time_str.replace("Z", "+00:00")).astimezone(self.tz)
                entry_date = dt.date()
            except Exception:
                continue

            # Populate hourly
            if dt >= now_dt:
                e_data = entry.get("data", {})
                h_temp = e_data.get("air_temperature")
                h_sym = e_data.get("symbol_code")
                if h_temp is not None and h_sym is not None:
                    h_cond_key = SMHI_CONDITION_MAP.get(int(h_sym), "clear")
                    hourly_forecast.append({
                        "time_label": self.get_hour_label(dt),
                        "temp": self.convert_temp(h_temp),
                        "icon": UNIFIED_ICONS.get(h_cond_key, "sun"),
                        "condition": self.translate(h_cond_key, h_cond_key.replace("_", " ").title())
                    })

            # Populate daily (strictly after today)
            if entry_date <= today_val:
                continue

            if entry_date not in daily_groups:
                daily_groups[entry_date] = []
            daily_groups[entry_date].append((dt, entry.get("data", {})))

        forecast_list = []
        for d in sorted(daily_groups.keys()):
            entries = daily_groups[d]
            temps = [e[1].get("air_temperature") for e in entries if e[1].get("air_temperature") is not None]
            if not temps:
                continue

            t_max = max(temps)
            t_min = min(temps)

            # Midday icon (closest to 12:00 local time)
            midday_entry = min(
                entries,
                key=lambda e: abs(datetime.combine(d, time(12, 0), tzinfo=self.tz) - e[0])
            )
            midday_sym = int(midday_entry[1].get("symbol_code", 1))
            f_cond_key = SMHI_CONDITION_MAP.get(midday_sym, "clear")

            forecast_list.append({
                "day_name": self.get_day_label(d, today_val),
                "temp_min": self.convert_temp(t_min),
                "temp_max": self.convert_temp(t_max),
                "icon": UNIFIED_ICONS.get(f_cond_key, "sun"),
                "condition": self.translate(f_cond_key, f_cond_key.replace("_", " ").title())
            })

        return {
            "current": {
                "temp": self.convert_temp(curr_temp),
                "icon": UNIFIED_ICONS.get(cond_key, "sun"),
                "condition": self.translate(cond_key, cond_key.replace("_", " ").title()),
                "wind_speed": self.convert_wind_speed(curr_wind),
                "wind_dir": self.translate(get_wind_direction_cardinal(curr_wind_deg)),
                "precipitation": round(curr_precip, 1),
                "provider_name": "SMHI"
            },
            "forecast": forecast_list[:self.forecast_days],
            "hourly_forecast": hourly_forecast[:self.forecast_hours]
        }

    def parse_open_meteo(self, data: dict, today_date: date) -> dict:
        if not data or "current" not in data:
            return {}
            
        current = data["current"]
        daily = data.get("daily", {})
        
        # Resolve now_dt and today_val for relative date/time calculations
        if isinstance(today_date, datetime):
            now_dt = today_date
            today_val = today_date.date()
        else:
            now_dt = datetime.combine(today_date, time.min, tzinfo=self.tz)
            today_val = today_date

        curr_temp = current.get("temperature_2m", 0.0)
        curr_wind = current.get("wind_speed_10m", 0.0)
        curr_wind_deg = current.get("wind_direction_10m", 0)
        curr_precip = current.get("precipitation", 0.0)
        curr_code = current.get("weather_code", 0)
        
        cond_key = WMO_CONDITION_MAP.get(curr_code, "clear")
        
        # Daily forecast
        forecast_list = []
        if daily and "time" in daily:
            times = daily["time"]
            codes = daily.get("weather_code", [])
            max_temps = daily.get("temperature_2m_max", [])
            min_temps = daily.get("temperature_2m_min", [])
            
            for i, time_str in enumerate(times):
                try:
                    d = date.fromisoformat(time_str)
                except Exception:
                    continue
                    
                if d <= today_val:
                    continue
                    
                f_code = codes[i] if i < len(codes) else 0
                t_max = max_temps[i] if i < len(max_temps) else 0.0
                t_min = min_temps[i] if i < len(min_temps) else 0.0
                
                f_cond_key = WMO_CONDITION_MAP.get(f_code, "clear")
                
                forecast_list.append({
                    "day_name": self.get_day_label(d, today_val),
                    "temp_min": self.convert_temp(t_min),
                    "temp_max": self.convert_temp(t_max),
                    "icon": UNIFIED_ICONS.get(f_cond_key, "sun"),
                    "condition": self.translate(f_cond_key, f_cond_key.replace("_", " ").title())
                })

        # Hourly forecast
        hourly_forecast = []
        hourly = data.get("hourly", {})
        if hourly and "time" in hourly:
            h_times = hourly["time"]
            h_temps = hourly.get("temperature_2m", [])
            h_codes = hourly.get("weather_code", [])
            for i, time_str in enumerate(h_times):
                try:
                    dt = datetime.fromisoformat(time_str).replace(tzinfo=self.tz)
                except Exception:
                    continue

                if dt < now_dt:
                    continue

                h_temp = h_temps[i] if i < len(h_temps) else None
                h_code = h_codes[i] if i < len(h_codes) else None
                if h_temp is None or h_code is None:
                    continue

                h_cond_key = WMO_CONDITION_MAP.get(h_code, "clear")
                hourly_forecast.append({
                    "time_label": self.get_hour_label(dt),
                    "temp": self.convert_temp(h_temp),
                    "icon": UNIFIED_ICONS.get(h_cond_key, "sun"),
                    "condition": self.translate(h_cond_key, h_cond_key.replace("_", " ").title())
                })
                
        return {
            "current": {
                "temp": self.convert_temp(curr_temp),
                "icon": UNIFIED_ICONS.get(cond_key, "sun"),
                "condition": self.translate(cond_key, cond_key.replace("_", " ").title()),
                "wind_speed": self.convert_wind_speed(curr_wind),
                "wind_dir": self.translate(get_wind_direction_cardinal(curr_wind_deg)),
                "precipitation": round(curr_precip, 1),
                "provider_name": "Open-Meteo"
            },
            "forecast": forecast_list[:self.forecast_days],
            "hourly_forecast": hourly_forecast[:self.forecast_hours]
        }

    def parse_weatherapi(self, data: dict, today_date: date) -> dict:
        if not data or "current" not in data:
            return {}
            
        current = data["current"]
        forecast = data.get("forecast", {}).get("forecastday", [])
        
        # Resolve now_dt and today_val for relative date/time calculations
        if isinstance(today_date, datetime):
            now_dt = today_date
            today_val = today_date.date()
        else:
            now_dt = datetime.combine(today_date, time.min, tzinfo=self.tz)
            today_val = today_date

        curr_temp = current.get("temp_c", 0.0)
        curr_wind_kph = current.get("wind_kph", 0.0)
        curr_wind = curr_wind_kph / 3.6  # Convert to m/s
        curr_wind_deg = current.get("wind_degree", 0)
        curr_precip = current.get("precip_mm", 0.0)
        curr_code = current.get("condition", {}).get("code", 1000)
        
        cond_key = WEATHERAPI_CONDITION_MAP.get(curr_code, "clear")
        
        # Daily forecast
        forecast_list = []
        hourly_forecast = []
        for day_entry in forecast:
            time_str = day_entry.get("date", "")
            try:
                d = date.fromisoformat(time_str)
            except Exception:
                continue
                
            # Parse daily (strictly after today)
            if d > today_val:
                day_data = day_entry.get("day", {})
                t_max = day_data.get("maxtemp_c", 0.0)
                t_min = day_data.get("mintemp_c", 0.0)
                f_code = day_data.get("condition", {}).get("code", 1000)
                
                f_cond_key = WEATHERAPI_CONDITION_MAP.get(f_code, "clear")
                
                forecast_list.append({
                    "day_name": self.get_day_label(d, today_val),
                    "temp_min": self.convert_temp(t_min),
                    "temp_max": self.convert_temp(t_max),
                    "icon": UNIFIED_ICONS.get(f_cond_key, "sun"),
                    "condition": self.translate(f_cond_key, f_cond_key.replace("_", " ").title())
                })

            # Parse hourly
            hours = day_entry.get("hour", [])
            for h_entry in hours:
                h_time_str = h_entry.get("time", "")
                try:
                    dt = datetime.strptime(h_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=self.tz)
                except Exception:
                    continue

                if dt < now_dt:
                    continue

                h_temp = h_entry.get("temp_c")
                h_code = h_entry.get("condition", {}).get("code")
                if h_temp is None or h_code is None:
                    continue

                h_cond_key = WEATHERAPI_CONDITION_MAP.get(h_code, "clear")
                hourly_forecast.append({
                    "time_label": self.get_hour_label(dt),
                    "temp": self.convert_temp(h_temp),
                    "icon": UNIFIED_ICONS.get(h_cond_key, "sun"),
                    "condition": self.translate(h_cond_key, h_cond_key.replace("_", " ").title())
                })
            
        return {
            "current": {
                "temp": self.convert_temp(curr_temp),
                "icon": UNIFIED_ICONS.get(cond_key, "sun"),
                "condition": self.translate(cond_key, cond_key.replace("_", " ").title()),
                "wind_speed": self.convert_wind_speed(curr_wind),
                "wind_dir": self.translate(get_wind_direction_cardinal(curr_wind_deg)),
                "precipitation": round(curr_precip, 1),
                "provider_name": "WeatherAPI"
            },
            "forecast": forecast_list[:self.forecast_days],
            "hourly_forecast": hourly_forecast[:self.forecast_hours]
        }

    def parse_openweathermap(self, data: dict, today_date: date) -> dict:
        if not data or "list" not in data:
            return {}
            
        entries = data["list"]
        if not entries:
            return {}
            
        # Resolve now_dt and today_val for relative date/time calculations
        if isinstance(today_date, datetime):
            now_dt = today_date
            today_val = today_date.date()
        else:
            now_dt = datetime.combine(today_date, time.min, tzinfo=self.tz)
            today_val = today_date

        # First entry as current
        first = entries[0]
        main_data = first.get("main", {})
        weather_list = first.get("weather", [])
        weather_obj = weather_list[0] if weather_list else {}
        
        curr_temp = main_data.get("temp", 0.0)
        curr_wind = first.get("wind", {}).get("speed", 0.0)
        curr_wind_deg = first.get("wind", {}).get("deg", 0)
        
        curr_precip = first.get("rain", {}).get("3h", 0.0) + first.get("snow", {}).get("3h", 0.0)
        curr_code = weather_obj.get("id", 800)
        
        cond_key = map_openweathermap_code(curr_code)
        
        # Group forecast daily and build hourly list
        daily_groups = {}
        hourly_forecast = []

        for entry in entries:
            ts = entry.get("dt")
            if not ts:
                continue
            try:
                dt = datetime.fromtimestamp(ts, self.tz)
                entry_date = dt.date()
            except Exception:
                continue
                
            # Hourly
            if dt >= now_dt:
                e_main = entry.get("main", {})
                h_temp = e_main.get("temp")
                e_weather = entry.get("weather", [])
                h_code = e_weather[0].get("id") if e_weather else None
                if h_temp is not None and h_code is not None:
                    h_cond_key = map_openweathermap_code(h_code)
                    hourly_forecast.append({
                        "time_label": self.get_hour_label(dt),
                        "temp": self.convert_temp(h_temp),
                        "icon": UNIFIED_ICONS.get(h_cond_key, "sun"),
                        "condition": self.translate(h_cond_key, h_cond_key.replace("_", " ").title())
                    })

            # Daily (strictly after today)
            if entry_date <= today_val:
                continue
                
            if entry_date not in daily_groups:
                daily_groups[entry_date] = []
            daily_groups[entry_date].append((dt, entry))
            
        forecast_list = []
        for d in sorted(daily_groups.keys()):
            day_entries = daily_groups[d]
            temps_max = [e[1].get("main", {}).get("temp_max") for e in day_entries if e[1].get("main", {}).get("temp_max") is not None]
            temps_min = [e[1].get("main", {}).get("temp_min") for e in day_entries if e[1].get("main", {}).get("temp_min") is not None]
            if not temps_max or not temps_min:
                continue
                
            t_max = max(temps_max)
            t_min = min(temps_min)
            
            # Midday icon
            midday_entry = min(day_entries, key=lambda e: abs(datetime.combine(d, time(12, 0), tzinfo=self.tz) - e[0]))
            midday_weather = midday_entry[1].get("weather", [])
            midday_code = midday_weather[0].get("id", 800) if midday_weather else 800
            
            f_cond_key = map_openweathermap_code(midday_code)
            
            forecast_list.append({
                "day_name": self.get_day_label(d, today_val),
                "temp_min": self.convert_temp(t_min),
                "temp_max": self.convert_temp(t_max),
                "icon": UNIFIED_ICONS.get(f_cond_key, "sun"),
                "condition": self.translate(f_cond_key, f_cond_key.replace("_", " ").title())
            })
            
        return {
            "current": {
                "temp": self.convert_temp(curr_temp),
                "icon": UNIFIED_ICONS.get(cond_key, "sun"),
                "condition": self.translate(cond_key, cond_key.replace("_", " ").title()),
                "wind_speed": self.convert_wind_speed(curr_wind),
                "wind_dir": self.translate(get_wind_direction_cardinal(curr_wind_deg)),
                "precipitation": round(curr_precip, 1),
                "provider_name": "OpenWeather"
            },
            "forecast": forecast_list[:self.forecast_days],
            "hourly_forecast": hourly_forecast[:self.forecast_hours]
        }

    async def run_loop(self, broadcast_func):
        logger.info(f"Starting {self.name} run loop")
        while True:
            try:
                # Get current date/time in module local timezone
                now_dt = datetime.now(self.tz)
                
                # Fetch data based on selected provider
                weather_info = {}
                self.last_error = None
                if self.provider == "smhi":
                    raw_data = await self.fetch_api(
                        f"https://opendata-download-metfcst.smhi.se/api/category/snow1g/version/1/"
                        f"geotype/point/lon/{round(self.longitude, 6)}/lat/{round(self.latitude, 6)}/data.json"
                    )
                    weather_info = self.parse_smhi(raw_data, now_dt)

                elif self.provider == "open_meteo":
                    raw_data = await self.fetch_api("https://api.open-meteo.com/v1/forecast", {
                        "latitude": round(self.latitude, 4), "longitude": round(self.longitude, 4),
                        "current": "temperature_2m,wind_speed_10m,wind_direction_10m,precipitation,weather_code",
                        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                        "hourly": "temperature_2m,weather_code", "timezone": self.tz.key,
                    })
                    weather_info = self.parse_open_meteo(raw_data, now_dt)

                elif self.provider == "weatherapi":
                    if not self.weatherapi_key:
                        weather_info = {"error": self.translate("error_api_key", "API Key required")}
                    else:
                        raw_data = await self.fetch_api("https://api.weatherapi.com/v1/forecast.json", {
                            "key": self.weatherapi_key, "q": f"{self.latitude},{self.longitude}",
                            "days": self.forecast_days + 1, "aqi": "no",
                        })
                        weather_info = self.parse_weatherapi(raw_data, now_dt)

                elif self.provider == "openweathermap":
                    if not self.openweathermap_key:
                        weather_info = {"error": self.translate("error_api_key", "API Key required")}
                    else:
                        raw_data = await self.fetch_api("https://api.openweathermap.org/data/2.5/forecast", {
                            "lat": self.latitude, "lon": self.longitude,
                            "appid": self.openweathermap_key, "units": "metric",
                        })
                        weather_info = self.parse_openweathermap(raw_data, now_dt)

                else:
                    logger.error(f"Unknown weather provider: {self.provider}")
                    weather_info = {"error": f"Unknown provider: {self.provider}"}

                # Nothing to show: say why
                if not weather_info:
                    weather_info = {"error": self.translate("error_key_rejected", "The API key was rejected. Check it in the module's settings.")
                                    if self.last_error == "rejected" else self.translate("error_fetch", "Fetch failed")}

                # Render template
                html = self.render_template(
                    "widget.html",
                    weather=weather_info,
                    show_header=self.show_header,
                    show_wind=self.show_wind,
                    show_precipitation=self.show_precipitation,
                    show_forecast=self.show_forecast,
                    forecast_type=self.forecast_type,
                    layout=self.layout,
                    temp_unit_label=self.get_temp_unit_label(),
                    wind_unit_label=self.get_wind_unit_label(),
                    last_checked=datetime.now().strftime("%H:%M")
                )
                
                # Broadcast updates
                logger.info(f"Broadcasting update for {self.name} using provider {self.provider}")
                await broadcast_func(self.name, html)
                
            except asyncio.CancelledError:
                logger.info(f"Stopping WeatherModule event loop.")
                raise
            except Exception as e:
                logger.error(f"Error in WeatherModule loop: {e}", exc_info=True)
                
            await asyncio.sleep(self.interval)
