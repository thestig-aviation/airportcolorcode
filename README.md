# Airport Color Code Map

Generate and publish a color-coded TAF map for airports using data from https://aviation.met.no.

## Capabilities

- Fetches all available TAF locations from the MET Aviation API.
- Fetches per-airport IWXXM payloads and parses:
	- issue time
	- forecast validity period (valid from / valid to) and whether the forecast is valid at current UTC time
	- prevailing visibility
	- cloud ceiling drivers (`VV`, `BKN`, `OVC`)
	- CAVOK (`cloudAndVisibilityOK`) presence
	- TS (thunderstorm) weather presence plus CB (cumulonimbus) and TCU (towering cumulus)
- Converts units from IWXXM (meters, km, miles, feet) to:
	- visibility in km
	- ceiling in ft
- Calculates UK/European colour state category per airport:
	- `BLU`, `WHT`, `GRN`, `YLO1`, `YLO2`, `AMB`, `RED`
- Renders an interactive Folium map with:
	- color-coded airport markers
	- gray marker (`#969696`) and label `Forecast Unavailable` when no current TAF is available
	- tooltip with ICAO and color code
	- popup with issue time, color code, ceiling and visibility
	- human-friendly unavailable reason in popup (`No current TAF`, `TAF not valid at current time`, `TAF data unavailable`)
	- CAVOK-aware popup display (`Ceiling/VV: CAVOK`, `Visibility: CAVOK`) when CAVOK drives BLU conditions
	- persistent ICAO labels
	- TS/CB/TCU symbol overlay for airports with convective weather in TAF
	- Priority order when multiple are present: TS, then CB, then TCU
	- color-state legend panel
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
- `taf_client.py`: TAF list retrieval and concurrent per-airport IWXXM enrichment (fetched in parallel via `ThreadPoolExecutor`).
- `iwxxm_parser.py`: IWXXM XML parsing, unit conversion helpers, and delegation to logic for weather code interpretation. Exposes the `ParsedConditions` namedtuple returned by `parse_iwxxm_conditions`.
- `logic.py`: Centralized business logic including:
  - Colour state rules (UK/European aviation standards)
  - Convective weather detection (TS/CB/TCU code matching)
  - Convective symbol priority resolution (TS > CB > TCU)
  - Forecast availability display logic (gray dots, unavailable reasons)
  - Issue-time formatting and display value generation
- `map_renderer.py`: Folium map rendering, marker drawing, legend, and icon overlays (uses logic.py for business rules).
- `html_postprocess.py`: HTML notice/countdown injection and map auto-refresh behavior.
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
