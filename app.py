"""Top-level orchestration: fetch TAF data, enrich each airport with IWXXM conditions, build the map, and post-process the HTML output."""
from config import (
    DEFAULT_OUTPUT_FILE,
    TS_ICON_LOCAL_NAME,
    TS_ICON_PATH,
)
from html_postprocess import postprocess_generated_html
from map_renderer import (
    build_map,
    ensure_local_icon,
)
from taf_client import enrich_features_with_iwxxm, fetch_taf_data


def main():
    print("Fetching TAF data...")
    data = fetch_taf_data()
    ts_icon_uri = ensure_local_icon(TS_ICON_PATH, TS_ICON_LOCAL_NAME)

    features = data.get("features", [])
    print(f"Found {len(features)} TAF locations.")
    print("Fetching per-location IWXXM data...")
    enrich_features_with_iwxxm(features)

    m = build_map(features, ts_icon_uri)
    m.save(str(DEFAULT_OUTPUT_FILE))

    postprocess_generated_html(DEFAULT_OUTPUT_FILE, features)
    print(f"Map saved to {DEFAULT_OUTPUT_FILE} with auto-refresh enabled")
