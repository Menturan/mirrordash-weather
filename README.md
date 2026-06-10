# mirrordash-weather

Weather forecast widget for MirrorDash. Displays current conditions and a configurable-length daily forecast strip using one of four weather provider APIs.

## Providers

| `provider` value | API | Free tier | API key required |
|-----------------|-----|-----------|-----------------|
| `"smhi"` | [SMHI Open Data](https://opendata-download-metfcst.smhi.se/) (`pmp3g/v2`) | Unlimited | ❌ No |
| `"open_meteo"` | [Open-Meteo](https://open-meteo.com/) | Unlimited | ❌ No |
| `"weatherapi"` | [WeatherAPI.com](https://www.weatherapi.com/) | 1 M calls/month | ✅ Yes |
| `"openweathermap"` | [OpenWeatherMap](https://openweathermap.org/api) | 1 000 calls/day | ✅ Yes |

**SMHI** is recommended for Sweden and the Nordics — no account or key required. **Open-Meteo** is recommended for global free use.

## Installation

```bash
uv pip install -e ./modules/mirrordash-weather
```

## Configuration

Add the module to `config.json` under `"modules"`:

```json
"mirrordash-weather": {
  "enabled": true,
  "position": "top_right",
  "interval": 900,
  "provider": "smhi",
  "weatherapi_key": "",
  "openweathermap_key": "",
  "show_header": true,
  "show_wind": true,
  "show_precipitation": true,
  "show_forecast": true,
  "forecast_days": 4
}
```

### Config Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `provider` | string | `"smhi"` | Weather data source. One of: `"smhi"`, `"open_meteo"`, `"weatherapi"`, `"openweathermap"` |
| `weatherapi_key` | string | `""` | Required when `provider = "weatherapi"` |
| `openweathermap_key` | string | `""` | Required when `provider = "openweathermap"` |
| `latitude` | number | — | Override coordinates. Falls back to `globals.latitude` |
| `longitude` | number | — | Override coordinates. Falls back to `globals.longitude` |
| `show_header` | boolean | `true` | Show/hide the "WEATHER" section header |
| `show_wind` | boolean | `true` | Show/hide wind speed and direction |
| `show_precipitation` | boolean | `true` | Show/hide precipitation value |
| `show_forecast` | boolean | `true` | Show/hide daily forecast strip |
| `forecast_days` | integer | `4` | Number of future days to display (1–7) |

### Inherited Global Settings

Coordinates, timezone, and units are read automatically from the `globals` block in `config.json` (configurable via the Admin Dashboard → Configuration tab):

| Global key | Effect |
|-----------|--------|
| `latitude` / `longitude` | Location coordinates (used unless overridden above) |
| `timezone` | Used for daily forecast grouping and date labels |
| `temperature_unit` | `"C"` (Celsius) or `"F"` (Fahrenheit) |
| `distance_unit` | `"km"` → wind in m/s, `"miles"` → wind in mph |
| `language` | Locale for day-name formatting (e.g. `"sv"`, `"en"`, `"de"`) |

## Obtaining API Keys

**WeatherAPI.com:**
1. Register at [weatherapi.com](https://www.weatherapi.com/) (free tier: 1 M calls/month).
2. Copy your key from the dashboard.
3. Enter it in `weatherapi_key` in `config.json` or via Admin → Modules.

**OpenWeatherMap:**
1. Register at [openweathermap.org](https://openweathermap.org/api) (free tier: 1 000 calls/day).
2. Generate an API key (AppID) from your account.
3. Enter it in `openweathermap_key` in `config.json` or via Admin → Modules.

## Screenshot

![Screenshot](screenshot.png)
