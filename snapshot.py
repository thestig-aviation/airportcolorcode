"""Render a PNG snapshot of the published airport color code map.

Loads the live page in a headless browser, fits the map to the requested
bounding box, optionally sets the TAF time-slider, and saves a screenshot.

Usage (CLI) — one-shot snapshot
--------------------------------
    python snapshot.py --bbox "min_lon,min_lat,max_lon,max_lat" \\
                       --buffer 0.5 \\
                       --start "2026-06-08T12:00Z" \\
                       --end   "2026-06-08T18:00Z" \\
                       --output snapshot.png \\
                       [--width 1280] [--height 900]

Usage (CLI) — HTTP server
--------------------------
    
    pip install flask
    python snapshot.py --serve                        # listens on 127.0.0.1:8000

    Then call:
        GET http://localhost:8000/snapshot
            ?bbox=0,58,15,65
            &buffer=0.5
            &start=2026-06-08T12:00Z
            &end=2026-06-08T18:00Z
            &width=1280
            &height=900

    The response is a raw PNG (Content-Type: image/png).

``--start`` / ``--end`` accept any ISO-8601 UTC string (trailing Z accepted).
Omitting them leaves the slider at the page's default position.

Requires
--------
    pip install playwright flask
    playwright install chromium
"""
import argparse
import os
import tempfile
from datetime import datetime, timezone

MAP_URL = "https://thestig-aviation.github.io/airportcolorcode/"
DEFAULT_OUTPUT = "snapshot.png"


def _iso_to_ms(iso_str: str) -> int:
    """Parse an ISO-8601 UTC string and return Unix milliseconds."""
    s = iso_str.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def take_snapshot(
    bbox: tuple,
    buffer_deg: float = 0.5,
    slider_start: str | None = None,
    slider_end: str | None = None,
    output: str = DEFAULT_OUTPUT,
    width: int = 1280,
    height: int = 900,
    timeout_ms: int = 25000,
) -> str:
    """Render the map as a PNG and return the saved output path.

    Parameters
    ----------
    bbox:
        ``(min_lon, min_lat, max_lon, max_lat)`` in WGS-84 decimal degrees.
    buffer_deg:
        Padding added to every side of the bounding box, in degrees.
    slider_start:
        UTC ISO-8601 string for the *start* handle of the TAF time slider.
    slider_end:
        UTC ISO-8601 string for the *end* handle of the TAF time slider.
    output:
        Destination file path for the PNG.
    width:
        Viewport width in pixels.
    height:
        Viewport height in pixels.
    timeout_ms:
        Maximum time to wait for the page to load, in milliseconds.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "playwright is not installed.\n"
            "Run:  pip install playwright && playwright install chromium"
        )

    min_lon, min_lat, max_lon, max_lat = bbox
    min_lat -= buffer_deg
    min_lon -= buffer_deg
    max_lat += buffer_deg
    max_lon += buffer_deg

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(MAP_URL, wait_until="networkidle", timeout=timeout_ms)

        # Fit the Leaflet map to the (buffered) bounding box.
        # Folium stores the L.Map instance on window under an auto-generated key
        # (e.g. window.map_a1b2c3…). Walk all window keys to find it.
        page.evaluate(f"""
            (function() {{
                var map = null;
                for (var k in window) {{
                    var v = window[k];
                    if (v && typeof v.fitBounds === 'function' &&
                            typeof v.getCenter === 'function') {{
                        map = v;
                        break;
                    }}
                }}
                if (!map) return;
                map.fitBounds([[{min_lat}, {min_lon}], [{max_lat}, {max_lon}]]);
            }})();
        """)

        # Set the time slider if start and end are both provided.
        if slider_start is not None and slider_end is not None:
            start_ms = _iso_to_ms(slider_start)
            end_ms = _iso_to_ms(slider_end)
            page.evaluate(f"""
                (function() {{
                    // BASE_MS and TOTAL_HOURS are const inside the slider IIFE;
                    // extract them from the raw script text.
                    var base_ms = null, total_hours = null;
                    for (var s of document.scripts) {{
                        var m1 = s.textContent.match(/const BASE_MS\\s*=\\s*(\\d+)/);
                        var m2 = s.textContent.match(/const TOTAL_HOURS\\s*=\\s*(\\d+)/);
                        if (m1) base_ms = parseInt(m1[1]);
                        if (m2) total_hours = parseInt(m2[1]);
                        if (base_ms !== null && total_hours !== null) break;
                    }}
                    if (base_ms === null || total_hours === null) return;
                    function clamp(v, lo, hi) {{ return Math.max(lo, Math.min(hi, v)); }}
                    var sv = clamp(Math.round(({start_ms} - base_ms) / 3600000), 0, total_hours - 1);
                    var ev = clamp(Math.round(({end_ms}   - base_ms) / 3600000), sv + 1, total_hours);
                    var sEl = document.getElementById('taf-slider-start');
                    var eEl = document.getElementById('taf-slider-end');
                    if (sEl && eEl) {{
                        sEl.value = sv;
                        eEl.value = ev;
                        // Fire input events so the map updates.
                        sEl.dispatchEvent(new Event('input'));
                        eEl.dispatchEvent(new Event('input'));
                    }}
                }})();
            """)

        # Let map tiles and marker re-renders settle.
        page.wait_for_timeout(2000)

        page.screenshot(path=output, full_page=False)
        browser.close()

    return output


# ---------------------------------------------------------------------------
# Flask HTTP server
# ---------------------------------------------------------------------------

def create_app():
    """Create and return the Flask application."""
    try:
        from flask import Flask, Response, request
    except ImportError:
        raise SystemExit(
            "flask is not installed.\n"
            "Run:  pip install flask"
        )

    app = Flask(__name__)

    @app.route("/snapshot")
    def snapshot_endpoint():
        # --- bbox (required) ---
        bbox_str = request.args.get("bbox")
        if not bbox_str:
            return Response("Missing required parameter: bbox", status=400)
        try:
            parts = [float(x.strip()) for x in bbox_str.split(",")]
            if len(parts) != 4:
                raise ValueError
            bbox = tuple(parts)
        except ValueError:
            return Response(
                "bbox must be four comma-separated floats: min_lon,min_lat,max_lon,max_lat",
                status=400,
            )

        # --- optional params ---
        try:
            buffer_deg = float(request.args.get("buffer", 0.5))
            width = int(request.args.get("width", 1280))
            height = int(request.args.get("height", 900))
        except ValueError as exc:
            return Response(f"Invalid parameter: {exc}", status=400)

        slider_start = request.args.get("start") or None
        slider_end = request.args.get("end") or None

        # --- render to a temp file, return bytes ---
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        try:
            take_snapshot(
                bbox=bbox,
                buffer_deg=buffer_deg,
                slider_start=slider_start,
                slider_end=slider_end,
                output=tmp.name,
                width=width,
                height=height,
            )
            with open(tmp.name, "rb") as f:
                png_bytes = f.read()
        finally:
            os.unlink(tmp.name)

        return Response(png_bytes, mimetype="image/png")

    return app


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the Flask HTTP server."""
    app = create_app()
    print(f"Snapshot server running at http://{host}:{port}/snapshot")
    app.run(host=host, port=port)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_bbox(s: str) -> tuple:
    parts = [float(x.strip()) for x in s.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "bbox must be four comma-separated floats: min_lon,min_lat,max_lon,max_lat"
        )
    return tuple(parts)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render a PNG snapshot of the airport color code map.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--serve", action="store_true",
        help="Start the HTTP server instead of taking a one-shot snapshot.",
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Host address for the HTTP server (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Port for the HTTP server (default: 8000).",
    )
    parser.add_argument(
        "--bbox", type=_parse_bbox,
        metavar="min_lon,min_lat,max_lon,max_lat",
        help="Bounding box in WGS-84 decimal degrees. Required when not using --serve.",
    )
    parser.add_argument(
        "--buffer", type=float, default=0.5, metavar="DEG",
        help="Extra padding on each side of the bbox in degrees (default: 0.5).",
    )
    parser.add_argument(
        "--start", dest="slider_start", default=None, metavar="ISO8601",
        help="UTC ISO-8601 datetime for the time-slider start handle.",
    )
    parser.add_argument(
        "--end", dest="slider_end", default=None, metavar="ISO8601",
        help="UTC ISO-8601 datetime for the time-slider end handle.",
    )
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT,
        help=f"Output PNG file path (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--width", type=int, default=1280,
        help="Viewport width in pixels (default: 1280).",
    )
    parser.add_argument(
        "--height", type=int, default=900,
        help="Viewport height in pixels (default: 900).",
    )
    args = parser.parse_args()

    if args.serve:
        serve(host=args.host, port=args.port)
        return

    if args.bbox is None:
        parser.error("--bbox is required when not using --serve")

    out = take_snapshot(
        bbox=args.bbox,
        buffer_deg=args.buffer,
        slider_start=args.slider_start,
        slider_end=args.slider_end,
        output=args.output,
        width=args.width,
        height=args.height,
    )
    print(f"Snapshot saved to: {out}")


if __name__ == "__main__":
    main()
