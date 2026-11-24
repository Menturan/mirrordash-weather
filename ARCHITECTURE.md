# mirrordash-weather — Architectural Decisions Record (ADR)

This document records the architectural decisions made during the design and development of the weather forecast module.

## 1. Unified Multi-Provider Weather Data Model
* **Decision**: Decoupled the weather module frontend (HTML/CSS/Jinja2 template) from specific weather provider APIs by implementing a unified Python weather dictionary model. Supported APIs include SMHI (`snow1g/version/1`), Open-Meteo, WeatherAPI.com, and OpenWeatherMap.
* **Rationale**: Weather sites and APIs change formats, endpoints, and codes frequently. Decoupling them allows the HTML layout, translations, and Lucide icons to remain completely unchanged even if backend APIs update or new weather providers are added. It also ensures consistent localization, temperature/wind unit formatting, and cardinal wind abbreviations across all selected providers.

## 2. SMHI API Response Structure
* **Decision**: The `mirrordash-weather` module uses the SMHI `snow1g/version/1` point forecast endpoint. Parsing reads the `timeSeries` camelCase array, each entry's `validTime` field, and extracts weather values directly from the flat parameter dictionary representation.
* **Rationale**: The SMHI opendata `snow1g` API uses a flat dictionary representation for parameters in each time series entry. Documenting this here prevents documentation drift and keeps it in sync with the codebase.

## 3. Local Readings From Other Modules
* **Decision**: The card can show the outdoor temperature and humidity from the owner's own sensor. The module knows no sender (not Home Assistant, not anyone): the owner types the public event name in a setting, and the module subscribes to exactly that name (the setting is the allow-list). The payload is the shared "reading" shape `{"value": <number>, "unit": <text>}`; other keys are ignored. Temperature accepts `°C`, `C`, `°F`, `F` (stored as °C, plausible range -90 to 60 °C); humidity accepts `%` (0 to 100). A bool, NaN, infinity, text, an unknown unit or a value out of range is dropped, since another module's data is untrusted.
* **How**: `local_readings.py` keeps the last valid value of each reading with its `time.monotonic()` moment; a reading is fresh for 600 s. A valid event calls `self.changed.set()` at once (render reuses the young provider answer from `fetch_json`, so no extra API call) and plans one more render 601 s later, so the provider's temperature returns even with a long `interval`. In `render` a fresh temperature replaces only `weather.current.temp`, converted and rounded like the provider's; forecast, wind and conditions stay from the provider, and a weather error is left alone. A small house icon marks the values from the own sensor.
* **Rationale**: Modules stay decoupled: any module that publishes a reading can feed the card, and a wrong or silent sensor can never leave a stale value on the mirror.
