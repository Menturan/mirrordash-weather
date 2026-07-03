# mirrordash-weather — Architectural Decisions Record (ADR)

This document records the architectural decisions made during the design and development of the weather forecast module.

## 1. Unified Multi-Provider Weather Data Model
* **Decision**: Decoupled the weather module frontend (HTML/CSS/Jinja2 template) from specific weather provider APIs by implementing a unified Python weather dictionary model. Supported APIs include SMHI (`snow1g/version/1`), Open-Meteo, WeatherAPI.com, and OpenWeatherMap.
* **Rationale**: Weather sites and APIs change formats, endpoints, and codes frequently. Decoupling them allows the HTML layout, translations, and Lucide icons to remain completely unchanged even if backend APIs update or new weather providers are added. It also ensures consistent localization, temperature/wind unit formatting, and cardinal wind abbreviations across all selected providers.

## 2. SMHI API Response Structure
* **Decision**: The `mirrordash-weather` module uses the SMHI `snow1g/version/1` point forecast endpoint. Parsing reads the `timeSeries` camelCase array, each entry's `validTime` field, and extracts weather values directly from the flat parameter dictionary representation.
* **Rationale**: The SMHI opendata `snow1g` API uses a flat dictionary representation for parameters in each time series entry. Documenting this here prevents documentation drift and keeps it in sync with the codebase.
