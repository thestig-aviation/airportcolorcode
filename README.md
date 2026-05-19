# Airport Color Code Map

Generate and publish a color-coded TAF map for airports using data from https://aviation.met.no.

The script:
- Downloads TAF location data
- Enriches each location with IWXXM ceiling/visibility values
- Assigns UK/European color state categories (`BLU`, `WHT`, `GRN`, `YLO1`, `YLO2`, `AMB`, `RED`)
- Writes an interactive Folium map to `airport_color_codes.html`

## Repository Layout

- `airportcolorcode.py`: Main script
- `airport_color_codes.html`: Generated map output (can be published with GitHub Pages)
- `cb_symbol.png`: Optional local icon asset
- `.github/workflows/publish-map.yml`: Optional automation to regenerate and deploy map

## Quick Start

### 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Generate the map

```bash
python airportcolorcode.py
```

Output is written to:

- `airport_color_codes.html`

## Publish on GitHub Pages

This repository includes a workflow in `.github/workflows/publish-map.yml` that:
- Regenerates `airport_color_codes.html`
- Creates `index.html` from the generated map for GitHub Pages root
- Deploys that HTML as a GitHub Pages site

To enable it:
1. Push this folder as a GitHub repository.
2. In GitHub, open **Settings -> Pages**.
3. Under **Build and deployment**, select **Source: GitHub Actions**.
4. Run the workflow once manually from the **Actions** tab (or push to `main`).

After deployment, your map will be available at your Pages URL.

## Notes

- The map uses external CDN resources (Leaflet/Bootstrap/Folium assets), so internet access is required when viewing it.
- Data is fetched live from `aviation.met.no` each run.
- The script writes output relative to its own folder, making local and CI execution consistent.
