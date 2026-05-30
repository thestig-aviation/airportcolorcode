# Airport Color Code Map

Generate and publish a color-coded TAF map for airports using data from https://aviation.met.no.

## Capabilities

- Fetches all available TAF locations from the MET Aviation API.
- Parses each airport's IWXXM payload into a list of **`ForecastPeriod`** records, one per `MeteorologicalAerodromeForecast` element (base, TEMPO, BECMG, PROB…). Each period carries:
	- time bounds (`begin` / `end`)
	- change type (`BASE`, `TEMPORARY_FLUCTUATIONS`, `BECOMING`, …)
	- prevailing visibility and cloud ceiling (ft)
	- CAVOK flag
	- colour state (`BLU` … `RED`) and numeric **rank** (0 = RED … 6 = BLU)
	- convective flags: `has_ts`, `has_cb`, `has_tcu`
- **BECMG base-splitting** (`BECMG_BASE_SPLIT` flag in `config.py`): when a BECMG period carries explicit visibility or ceiling data, the enclosing BASE period is split at `becmg.end` — the pre-transition segment retains the original BASE conditions and a synthetic post-transition segment inherits the BECMG's conditions. Wind-only BECMGs (no vis, no ceiling, not CAVOK) are excluded from splitting and from worst/best rank computation so they cannot artificially inflate the colour state to BLU.
- Derives **worst** and **best** forecast conditions by comparing ranks across weather-bearing periods only (periods with explicit vis/ceiling/CAVOK):
	- worst = `min(rank)` → inner filled dot colour
	- best = `max(rank)` → outer ring colour
- Calculates UK/European colour state from a **table-driven** threshold lookup (`_COLOUR_STATE_THRESHOLDS`):
	- `BLU` ≥ 2500 ft and ≥ 8 km
	- `WHT` < 2500 ft or < 8 km
	- `GRN` < 1500 ft or < 5 km
	- `YLO1` < 700 ft or < 3.7 km
	- `YLO2` < 500 ft or < 2.5 km
	- `AMB` < 300 ft or < 1.6 km
	- `RED` < 200 ft or < 0.8 km
- Renders an interactive Folium map with:
	- **Concentric circle markers** per airport (all markers always present; JS controls colour and opacity via the time slider):
		- Inner filled circle (radius 10, class `airport-worst`): worst forecast state colour for the selected window
		- Outer ring (radius 16, weight 5, class `airport-best`): best forecast state colour; hidden (`opacity: 0`) when no weather data overlaps the selected window
		- Gray inner dot when no forecast data overlaps the selected window
	- tooltip: `ICAO: <worst state> / <best state>`
	- popup: issue time, worst state, best state, ceiling and visibility
	- CAVOK-aware popup display
	- human-friendly unavailable reason in popup
	- persistent ICAO labels
	- **Convective overlays**: all three symbol types (TS, CB, TCU) are rendered per airport that has any convective in its TAF, each with its own class (`airport-convective-ts`, `airport-convective-cb`, `airport-convective-tcu`). JS shows at most one (priority TS > CB > TCU) based on which periods overlap the selected time window.
	- **Legend** with colour-state reference, inner fill / outer ring explainer, and **checkboxes** to toggle worst dot, best ring, and convective overlays independently (checkbox state persists in `localStorage`).
- **Time slider** fixed at the bottom of the page:
	- dual-thumb range slider spanning the full TAF validity window
	- labels update live as thumbs are dragged
	- on every drag, `updateMapForWindow()` recomputes worst/best colour and convective visibility for every airport and applies changes immediately via Leaflet `setStyle` / `setOpacity`
	- slider position persists across auto-refresh via `localStorage` (stored as absolute UTC millisecond timestamps, clamped to the new TAF window on restore)
- Adds a centered transparent status notice in generated HTML:
	- `Airport Color Code — Prototype - not intended for operational use`
	- `Codebase changed: <timestamp>` (from latest commit on `main`)
	- `Last Issue Time: <timestamp> (<ICAO>)`
- Injects client-side auto-refresh logic:
	- countdown timer in lower-right corner
	- page reload at `:01`, `:16`, `:31`, `:46` past each hour
	- map center/zoom persisted in `localStorage` across refreshes

## Repository Layout

- `airportcolorcode.py`: Compatibility entrypoint used by local runs and GitHub Actions.
- `app.py`: Top-level orchestration for fetch, enrich, render, and post-processing.
- `config.py`: Shared constants, API URLs, colour state hex values, `UNAVAILABLE_COLOR`, local output/icon paths, and `BECMG_BASE_SPLIT` rollback flag.
- `taf_client.py`: TAF list retrieval and concurrent per-airport IWXXM enrichment (fetched in parallel via `ThreadPoolExecutor`). Serialises `ForecastPeriod` data as `parsedForecastPeriods` onto each feature's properties dict.
- `iwxxm_parser.py`: IWXXM XML parsing and unit conversion. Key exports:
  - `ForecastPeriod` — one record per forecast period; carries time bounds, change type, colour state, rank, ceiling, visibility, CAVOK, and convective flags.
  - `ParsedConditions` — top-level result; holds the `forecast_periods` list plus aggregated flags.
  - `_apply_becmg_base_splits` — splits the BASE period at weather-changing BECMG boundaries; skips wind-only BECMGs. Controlled by `BECMG_BASE_SPLIT` in `config.py`.
- `logic.py`: Centralised business logic:
  - `COLOUR_STATE_RANK` / `_COLOUR_STATE_THRESHOLDS` — rank dict and threshold table.
  - `colour_state_hex(state_code)` — hex colour lookup.
  - Convective detection helpers and priority resolution.
  - Forecast availability display logic.
- `map_renderer.py`: Folium map rendering. Builds concentric circle markers (initial colours from current-time state), always renders the best ring at `opacity: 0`, renders all three convective marker types for airports with any convective in their TAF (all initially hidden). After the loop, injects `window.LAYER_MAP`, `window.COLOUR_STATE_HEX`, and `window.UNAVAILABLE_HEX` as a `<script>` element for use by the slider JS.
- `html_postprocess.py`: Post-processing pipeline:
  - Status notice and auto-refresh injection.
  - Time slider HTML/CSS/JS block; embeds `AIRPORT_PERIODS` JSON and the `updateMapForWindow()` function which reads `LAYER_MAP` and `AIRPORT_PERIODS` to recolour markers on every slider event.
- `airport_color_codes.html`: Generated map output.
- `cb_symbol.png`, `tcu_symbol.png`, `ts_symbol.png`: Local icon assets.
- `.github/workflows/publish-map.yml`: GitHub Actions workflow (pip dependency caching enabled).

## Quick Start

### 1. Create and activate virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 1b. Create and activate a local mamba environment (Python 3.13)

```bash
mamba create -n airportcolorcode313 python=3.13 -c conda-forge -y
mamba activate airportcolorcode313
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Generate map

```bash
python airportcolorcode.py
```

Generated output: `airport_color_codes.html`

## GitHub Pages Deployment

Workflow file: `.github/workflows/publish-map.yml`

- Triggers: push to `main`, `workflow_dispatch`, scheduled every 15 minutes
- Build: installs Python 3.13 + cached pip dependencies, runs `airportcolorcode.py`, copies output to `index.html`, uploads Pages artifact
- Deploy: publishes artifact to GitHub Pages

Enable Pages:

1. Push repository to GitHub.
2. Open **Settings → Pages**.
3. Under **Build and deployment**, select **Source: GitHub Actions**.

## Operational Notes

- Individual airport IWXXM requests are fetched concurrently (up to 20 workers); per-airport failures do not stop the run.
- If the GitHub API is unreachable or rate-limited, `Codebase changed` displays as `unavailable`.
- Output path is fixed relative to script location for local and CI consistency.
- Set `BECMG_BASE_SPLIT = False` in `config.py` to disable BECMG base-splitting without any other code change.
- All UI state (slider position, checkbox toggles, map view) persists across auto-refresh via `localStorage`.

