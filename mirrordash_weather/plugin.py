import asyncio
import logging
import os
import hashlib
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import httpx
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
        
        # Writable paths
        self.data_dir = config.get("data_dir")
        self.cache_dir = config.get("cache_dir")
        
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
        
        self.temp_unit = global_cfg.get("temperature_unit", "C")
        self.dist_unit = global_cfg.get("distance_unit", "km")
        
        timezone_name = global_cfg.get("timezone", "Europe/Stockholm")
        try:
            self.tz = ZoneInfo(timezone_name)
        except Exception:
            self.tz = ZoneInfo("UTC")
            
        logger.info(
            f"Initializing WeatherModule: provider={self.provider}, lat={self.latitude}, "
            f"lon={self.longitude}, tz={timezone_name}, lang={self.lang}, units={self.temp_unit}/{self.dist_unit}"
        )

    def translate(self, key, default=None):
        return self.translations.get(key, default or key)

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

    async def fetch_api(self, client: httpx.AsyncClient, url: str, headers=None) -> dict:
        """Fetch weather data from URL, saving to cache or loading from cache on failure."""
        cache_filename = hashlib.md5(url.encode('utf-8')).hexdigest() + ".json"
        cache_path = os.path.join(self.cache_dir, cache_filename) if self.cache_dir else None
        
        try:
            logger.info(f"Fetching weather from {url}")
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                if cache_path:
                    try:
                        import json
                        with open(cache_path, "w", encoding="utf-8") as f:
                            json.dump(data, f)
                    except Exception as ce:
                        logger.warning(f"Could not save weather cache: {ce}")
                return data
            else:
                logger.warning(f"Weather API returned status {response.status_code} for {url}")
        except Exception as e:
            logger.warning(f"Failed to fetch weather data: {e}")
            
        # Fallback to cache
        if cache_path and os.path.exists(cache_path):
            try:
                import json
                logger.info(f"Using cached weather data from {cache_path}")
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as re:
                logger.error(f"Failed to read weather cache from {cache_path}: {re}")
                
        return {}

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
        for entry in timeseries:
            time_str = entry.get("time", "")
            if not time_str:
                continue
            try:
                dt = datetime.fromisoformat(time_str.replace("Z", "+00:00")).astimezone(self.tz)
                entry_date = dt.date()
            except Exception:
                continue

            if entry_date <= today_date:
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
                "day_name": self.get_day_label(d, today_date),
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
            "forecast": forecast_list[:self.forecast_days]
        }

    def parse_open_meteo(self, data: dict, today_date: date) -> dict:
        if not data or "current" not in data:
            return {}
            
        current = data["current"]
        daily = data.get("daily", {})
        
        curr_temp = current.get("temperature_2m", 0.0)
        curr_wind = current.get("wind_speed_10m", 0.0)
        curr_wind_deg = current.get("wind_direction_10m", 0)
        curr_precip = current.get("precipitation", 0.0)
        curr_code = current.get("weather_code", 0)
        
        cond_key = WMO_CONDITION_MAP.get(curr_code, "clear")
        
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
                    
                if d <= today_date:
                    continue
                    
                f_code = codes[i] if i < len(codes) else 0
                t_max = max_temps[i] if i < len(max_temps) else 0.0
                t_min = min_temps[i] if i < len(min_temps) else 0.0
                
                f_cond_key = WMO_CONDITION_MAP.get(f_code, "clear")
                
                forecast_list.append({
                    "day_name": self.get_day_label(d, today_date),
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
                "provider_name": "Open-Meteo"
            },
            "forecast": forecast_list[:self.forecast_days]
        }

    def parse_weatherapi(self, data: dict, today_date: date) -> dict:
        if not data or "current" not in data:
            return {}
            
        current = data["current"]
        forecast = data.get("forecast", {}).get("forecastday", [])
        
        curr_temp = current.get("temp_c", 0.0)
        curr_wind_kph = current.get("wind_kph", 0.0)
        curr_wind = curr_wind_kph / 3.6  # Convert to m/s for unified input
        curr_wind_deg = current.get("wind_degree", 0)
        curr_precip = current.get("precip_mm", 0.0)
        curr_code = current.get("condition", {}).get("code", 1000)
        
        cond_key = WEATHERAPI_CONDITION_MAP.get(curr_code, "clear")
        
        forecast_list = []
        for day_entry in forecast:
            time_str = day_entry.get("date", "")
            try:
                d = date.fromisoformat(time_str)
            except Exception:
                continue
                
            if d <= today_date:
                continue
                
            day_data = day_entry.get("day", {})
            t_max = day_data.get("maxtemp_c", 0.0)
            t_min = day_data.get("mintemp_c", 0.0)
            f_code = day_data.get("condition", {}).get("code", 1000)
            
            f_cond_key = WEATHERAPI_CONDITION_MAP.get(f_code, "clear")
            
            forecast_list.append({
                "day_name": self.get_day_label(d, today_date),
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
                "provider_name": "WeatherAPI"
            },
            "forecast": forecast_list[:self.forecast_days]
        }

    def parse_openweathermap(self, data: dict, today_date: date) -> dict:
        if not data or "list" not in data:
            return {}
            
        entries = data["list"]
        if not entries:
            return {}
            
        # First entry as current
        first = entries[0]
        main_data = first.get("main", {})
        weather_list = first.get("weather", [])
        weather_obj = weather_list[0] if weather_list else {}
        
        curr_temp = main_data.get("temp", 0.0)
        curr_wind = first.get("wind", {}).get("speed", 0.0)
        curr_wind_deg = first.get("wind", {}).get("deg", 0)
        
        # Calculate current precipitation from rain/snow structures
        curr_precip = first.get("rain", {}).get("3h", 0.0) + first.get("snow", {}).get("3h", 0.0)
        curr_code = weather_obj.get("id", 800)
        
        cond_key = map_openweathermap_code(curr_code)
        
        # Group forecast
        daily_groups = {}
        for entry in entries:
            ts = entry.get("dt")
            if not ts:
                continue
            try:
                dt = datetime.fromtimestamp(ts, self.tz)
                entry_date = dt.date()
            except Exception:
                continue
                
            if entry_date <= today_date:
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
                "day_name": self.get_day_label(d, today_date),
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
            "forecast": forecast_list[:self.forecast_days]
        }

    async def run_loop(self, broadcast_func):
        logger.info(f"Starting {self.name} run loop")
        while True:
            try:
                # Get current date in module local timezone
                today_date = datetime.now(self.tz).date()
                
                # Fetch data based on selected provider
                weather_info = {}
                async with httpx.AsyncClient(verify=True) as client:
                    if self.provider == "smhi":
                        # snow1g is the standard SMHI point forecast (replaces discontinued pmp3g)
                        url = (
                            f"https://opendata-download-metfcst.smhi.se/api/category/snow1g/version/1/"
                            f"geotype/point/lon/{round(self.longitude, 6)}/lat/{round(self.latitude, 6)}/data.json"
                        )
                        raw_data = await self.fetch_api(client, url)
                        weather_info = self.parse_smhi(raw_data, today_date)
                        
                    elif self.provider == "open_meteo":
                        url = (
                            f"https://api.open-meteo.com/v1/forecast?latitude={round(self.latitude, 4)}"
                            f"&longitude={round(self.longitude, 4)}&current=temperature_2m,wind_speed_10m,"
                            f"wind_direction_10m,precipitation,weather_code&daily=weather_code,"
                            f"temperature_2m_max,temperature_2m_min&timezone={self.tz.key}"
                        )
                        raw_data = await self.fetch_api(client, url)
                        weather_info = self.parse_open_meteo(raw_data, today_date)
                        
                    elif self.provider == "weatherapi":
                        if not self.weatherapi_key:
                            logger.error("WeatherAPI key is missing!")
                            weather_info = {"error": self.translate("error_api_key", "API Key required")}
                        else:
                            url = (
                                f"https://api.weatherapi.com/v1/forecast.json?key={self.weatherapi_key}"
                                f"&q={self.latitude},{self.longitude}&days={self.forecast_days + 1}&aqi=no"
                            )
                            raw_data = await self.fetch_api(client, url)
                            weather_info = self.parse_weatherapi(raw_data, today_date)
                            
                    elif self.provider == "openweathermap":
                        if not self.openweathermap_key:
                            logger.error("OpenWeatherMap key is missing!")
                            weather_info = {"error": self.translate("error_api_key", "API Key required")}
                        else:
                            url = (
                                f"https://api.openweathermap.org/data/2.5/forecast?lat={self.latitude}"
                                f"&lon={self.longitude}&appid={self.openweathermap_key}&units=metric"
                            )
                            raw_data = await self.fetch_api(client, url)
                            weather_info = self.parse_openweathermap(raw_data, today_date)
                            
                    else:
                        logger.error(f"Unknown weather provider: {self.provider}")
                        weather_info = {"error": f"Unknown provider: {self.provider}"}
                
                # Check for parsing failure
                if not weather_info:
                    weather_info = {"error": self.translate("error_fetch", "Fetch failed")}
                
                # Render template
                html = self.render_template(
                    "widget.html",
                    weather=weather_info,
                    show_header=self.show_header,
                    show_wind=self.show_wind,
                    show_precipitation=self.show_precipitation,
                    show_forecast=self.show_forecast,
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
