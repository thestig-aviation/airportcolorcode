# Airport Color Code Map

Generate and publish a color-coded TAF map for airports using data from https://aviation.met.no.

## Capabilities

- Fetches all available TAF locations from the MET Aviation API.
- Fetches per-airport IWXXM payloads and parses:
	- issue time
	- prevailing visibility
	- cloud ceiling drivers (`VV`, `BKN`, `OVC`)
	- CB (cumulonimbus) and TCU (towering cumulus) presence in cloud layers
- Converts units from IWXXM (meters, km, miles, feet) to:
	- visibility in km
	- ceiling in ft
- Calculates UK/European colour state category per airport:
	- `BLU`, `WHT`, `GRN`, `YLO1`, `YLO2`, `AMB`, `RED`
- Renders an interactive Folium map with:
	- color-coded airport markers
	- tooltip with ICAO and color code
	- popup with issue time, ceiling and visibility
	- persistent ICAO labels
	- CB/TCU symbol overlay for airports with convective cloud in TAF
	- CB priority when both CB and TCU are present in the same forecast
	- color-state legend panel
- Adds a centered transparent status notice in generated HTML:
	- `Airport Color Code — alpha version`
	- `Last Build: <timestamp>` (fetched from latest commit on `main` for `thestig-aviation/airportcolorcode`)
- Injects client-side auto-refresh logic into output HTML:
	- countdown timer visible in lower-right corner
	- automatic page reload at `:01`, `:16`, `:31`, `:46`
	- retains map center/zoom between refreshes using browser local storage

## Repository Layout

- `airportcolorcode.py`: Compatibility entrypoint used by local runs and GitHub Actions.
- `app.py`: Top-level orchestration for fetch, enrich, render, and post-processing.
- `config.py`: Shared constants, API URLs, and local output/icon paths.
- `taf_client.py`: TAF list retrieval and per-airport IWXXM enrichment.
- `iwxxm_parser.py`: IWXXM XML parsing and unit conversion helpers.
- `logic.py`: Issue-time formatting, condition parsing fallback, and colour-state rules.
- `map_renderer.py`: Folium map rendering, marker drawing, legend, and icon overlays.
- `html_postprocess.py`: HTML notice/countdown injection and map auto-refresh behavior.
- `airport_color_codes.html`: Generated map output.
- `cb_symbol.png`: Local icon asset used for CB markers.
- `tcu_symbol.png`: Local icon asset used for TCU markers.
- `.github/workflows/publish-map.yml`: GitHub Actions workflow for build and Pages deployment.

## Quick Start

### 1. Create and activate virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
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
	- installs Python 3.11 + dependencies
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
- The script gracefully continues if individual airport IWXXM requests fail.
- If GitHub API cannot be reached/rate-limited, `Last Build` is shown as `unavailable`.
- Output path is fixed relative to script location for local and CI consistency.
- Saved map view persistence is browser-specific (stored in `localStorage`).
