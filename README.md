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
- Derives **worst** and **best** forecast conditions by comparing period ranks:
	- worst = `min(rank)` across periods → inner filled dot
	- best = `max(rank)` across periods → outer ring
- Calculates UK/European colour state from a **table-driven** threshold lookup (`_COLOUR_STATE_THRESHOLDS`), ordered by `COLOUR_STATE_RANK`:
	- `BLU` ≥ 2500 ft and ≥ 8 km
	- `WHT` < 2500 ft or < 8 km
	- `GRN` < 1500 ft or < 5 km
	- `YLO1` < 700 ft or < 3.7 km
	- `YLO2` < 500 ft or < 2.5 km
	- `AMB` < 300 ft or < 1.6 km
	- `RED` < 200 ft or < 0.8 km
- Renders an interactive Folium map with:
	- **Concentric circle markers** per airport:
		- Inner filled circle (radius 10): worst forecast state colour
		- Outer ring (radius 16, weight 5): best forecast state colour
		- Gray inner dot only (no outer ring) when forecast is unavailable
	- tooltip: `ICAO: <worst state> / <best state>`
	- popup: issue time, worst state, best state, ceiling and visibility
	- CAVOK-aware popup display (`Ceiling/VV: CAVOK`, `Visibility: CAVOK`)
	- human-friendly unavailable reason in popup (`No current TAF`, `TAF not valid at current time`, `TAF data unavailable`)
	- persistent ICAO labels
	- TS/CB/TCU symbol overlay for airports with convective weather in TAF (priority: TS > CB > TCU)
	- colour-state legend with inner fill / outer ring explainer
- Adds a centered transparent status notice in generated HTML:
	- `Airport Color Code — Prototype - not intended for operational use` (displayed in red boldface)
	- `Codebase changed: <timestamp>` (fetched from latest commit on `main` for `thestig-aviation/airportcolorcode`)
	- `Last Issue Time: <timestamp> (<ICAO>)` from latest parsed airport issue time
- Injects client-side auto-refresh logic into output HTML:
	- countdown timer visible in lower-right corner
	- automatic page reload at `:01`, `:16`, `:31`, `:46`
	- retains map center/zoom between refreshes using browser local storage

## Repository Layout

- `airportcolorcode.py`: Compatibility entrypoint used by local runs and GitHub Actions.
- `app.py`: Top-level orchestration for fetch, enrich, render, and post-processing.
- `config.py`: Shared constants, API URLs, colour state hex values, `UNAVAILABLE_COLOR`, and local output/icon paths.
- `taf_client.py`: TAF list retrieval and concurrent per-airport IWXXM enrichment (fetched in parallel via `ThreadPoolExecutor`). Serialises `ForecastPeriod` data (including convective flags) as `parsedForecastPeriods` onto each feature's properties dict.
- `iwxxm_parser.py`: IWXXM XML parsing and unit conversion. Exports two namedtuples:
  - `ForecastPeriod` — one record per forecast period; carries time bounds, change type, colour state, rank, ceiling, visibility, and convective flags (`has_ts`, `has_cb`, `has_tcu`).
  - `ParsedConditions` — top-level result of `parse_iwxxm_conditions`; holds the `forecast_periods` list plus aggregated convective and availability flags.
- `logic.py`: Centralised business logic including:
  - `COLOUR_STATE_RANK` — numeric rank dict (RED=0 … BLU=6) used for period comparisons.
  - `_COLOUR_STATE_THRESHOLDS` — table-driven threshold list powering `get_colour_state`.
  - `colour_state_hex(state_code)` — hex colour lookup for a state code.
  - Convective weather detection helpers (`_is_thunderstorm_code`, `_is_cb_code`, `_is_tcu_code`).
  - Convective symbol priority resolution (`get_priority_convective_symbol`: TS > CB > TCU).
  - Forecast availability display logic (gray dots, unavailable reasons).
  - Issue-time formatting and display value generation.
- `map_renderer.py`: Folium map rendering — concentric circle markers (inner fill = worst state, outer ring = best state), convective overlays, legend, and ICAO labels. Reads `parsedForecastPeriods` to derive worst/best rank.
- `html_postprocess.py`: HTML notice/countdown injection and map auto-refresh behaviour.
- `airport_color_codes.html`: Generated map output.
- `cb_symbol.png`: Local icon asset used for CB markers.
- `tcu_symbol.png`: Local icon asset used for TCU markers.
- `ts_symbol.png`: Local icon asset used for TS markers.
- `.github/workflows/publish-map.yml`: GitHub Actions workflow for build and Pages deployment.

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

Rollback locally:

```bash
mamba deactivate
mamba activate airportcolorcode
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Generate map

```bash
python airportcolorcode.py
```

Generated output:

- `airport_color_codes.html`

## GitHub Pages Deployment

Workflow file: `.github/workflows/publish-map.yml`

Current workflow behavior:

- Triggers:
	- push to `main`
	- manual run (`workflow_dispatch`)
	- scheduled every 15 minutes (`*/15 * * * *`)
- Build job:
	- installs Python 3.13 + dependencies
	- runs `airportcolorcode.py`
	- copies `airport_color_codes.html` to `index.html`
	- uploads Pages artifact
- Deploy job:
	- publishes artifact to GitHub Pages

Enable Pages:

1. Push repository to GitHub.
2. Open **Settings -> Pages**.
3. Under **Build and deployment**, select **Source: GitHub Actions**.

## Operational Notes

- Live data and HTML assets depend on internet access.
- Individual airport IWXXM requests are fetched concurrently (up to 20 workers); failures are handled per-airport without stopping the run.
- If the GitHub API cannot be reached or is rate-limited, `Codebase changed` is shown as `unavailable`.
- Output path is fixed relative to script location for local and CI consistency.
- Saved map view persistence is browser-specific (stored in `localStorage`).
