"""
Convert parish GeoJSON files to PMTiles using QuickMapTools (browser automation).
Uses Playwright to launch Chrome, upload files, and download PMTiles output.

Usage:
    python convert_geojson_to_pmtiles.py                    # Convert all parishes
    python convert_geojson_to_pmtiles.py --parish Kingston  # Convert one parish
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Add project root for imports
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

# QuickMapTools - may show "PS-error" for some GeoJSON (GDAL limitation)
URL_QUICKMAP = "https://www.quickmaptools.com/geojson-to-pmtiles"
# Mapshifter - alternative, "intended for small datasets"
URL_MAPSHIFTER = "https://mapshifter.vercel.app/map"
URL = URL_QUICKMAP
PARISH_DATA = PROJECT_ROOT / "parish_data"
PMTILES_OUT = PROJECT_ROOT / "parish_data" / "pmtiles"
HEADLESS = False  # Set True to run without visible browser


def convert_file(page, geojson_path: Path, output_name: str, timeout_ms: int = 300000) -> bool:
    """Upload GeoJSON and download PMTiles from QuickMapTools."""
    geojson_path = Path(geojson_path).resolve()
    if not geojson_path.exists():
        print(f"  ERROR: File not found: {geojson_path}")
        return False

    print(f"  Uploading {geojson_path.name} ({geojson_path.stat().st_size / 1e6:.1f} MB)...")
    
    try:
        # File input - QuickMapTools typically uses input[type="file"]
        file_input = page.locator('input[type="file"]').first
        file_input.set_input_files(str(geojson_path), timeout=timeout_ms)
        
        # Wait for file to be processed
        page.wait_for_timeout(3000)
        
        # Scroll down to reveal Convert to PMTiles button
        page.evaluate("window.scrollBy(0, 400)")
        page.wait_for_timeout(1000)
        
        # Click "Convert to PMTiles" button to trigger conversion
        convert_btn = page.get_by_role("button", name="Convert to PMTiles")
        convert_btn.wait_for(state="visible", timeout=10000)
        convert_btn.click()
        
        # Wait for conversion (may take 30-60s for larger files)
        page.wait_for_timeout(15000)
        
        # Check for conversion error
        error_el = page.get_by_text("Conversion Error", exact=False).first
        if error_el.is_visible(timeout=2000):
            error_text = page.locator("[class*='error'], [class*='Error']").first.text_content(timeout=2000) or "Unknown"
            print(f"  Conversion failed: {error_text}")
            return False
        
        # Try to find and click download link/button
        download_btn = page.get_by_text("Download", exact=False).first
        if download_btn.is_visible(timeout=60000):  # Up to 60s for conversion
            with page.expect_download(timeout=60000) as download_info:
                download_btn.click()
            download = download_info.value
            out_path = PMTILES_OUT / f"{output_name}.pmtiles"
            download.save_as(str(out_path))
            print(f"  ✓ Saved to {out_path}")
            return True
        else:
            # Maybe different button text - try common variants
            for text in ["Download", "Save", "Export", "Get PMTiles"]:
                btn = page.get_by_role("button", name=text).or_(page.get_by_text(text)).first
                if btn.is_visible(timeout=5000):
                    with page.expect_download(timeout=60000) as download_info:
                        btn.click()
                    download = download_info.value
                    out_path = PMTILES_OUT / f"{output_name}.pmtiles"
                    download.save_as(str(out_path))
                    print(f"  ✓ Saved to {out_path}")
                    return True
            
            # Scroll to bottom and try again
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            download_btn = page.get_by_text("Download", exact=False).first
            if download_btn.is_visible(timeout=5000):
                with page.expect_download(timeout=60000) as download_info:
                    download_btn.click()
                download = download_info.value
                out_path = PMTILES_OUT / f"{output_name}.pmtiles"
                download.save_as(str(out_path))
                print(f"  ✓ Saved to {out_path}")
                return True
            
            # Take screenshot for debugging
            screenshot_path = PROJECT_ROOT / "conversion_debug.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"  Could not find download button. Screenshot saved to {screenshot_path}")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        page.screenshot(path=str(PROJECT_ROOT / "conversion_error.png"))
        return False


def main():
    parser = argparse.ArgumentParser(description="Convert GeoJSON to PMTiles via QuickMapTools")
    parser.add_argument("--parish", help="Convert single parish (e.g. Kingston)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--mapshifter", action="store_true", help="Use Mapshifter instead of QuickMapTools")
    args = parser.parse_args()

    PMTILES_OUT.mkdir(parents=True, exist_ok=True)

    # Map parish names to filenames
    parish_files = {
        "Hanover": "parcels_Hanover.geojson",
        "St. Elizabeth": "parcels_St__Elizabeth.geojson",
        "St. James": "parcels_St__James.geojson",
        "Trelawny": "parcels_Trelawny.geojson",
        "Westmoreland": "parcels_Westmoreland.geojson",
        "Clarendon": "parcels_Clarendon.geojson",
        "Manchester": "parcels_Manchester.geojson",
        "St. Ann": "parcels_St__Ann.geojson",
        "St. Catherine": "parcels_St__Catherine.geojson",
        "St. Mary": "parcels_St__Mary.geojson",
        "Kingston": "parcels_Kingston.geojson",
        "Portland": "parcels_Portland.geojson",
        "St. Andrew": "parcels_St__Andrew.geojson",
        "St. Thomas": "parcels_St__Thomas.geojson",
    }

    if args.parish:
        if args.parish not in parish_files:
            print(f"Unknown parish. Choose from: {', '.join(parish_files)}")
            sys.exit(1)
        to_convert = [(args.parish, parish_files[args.parish])]
    else:
        to_convert = list(parish_files.items())

    headless = args.headless or HEADLESS
    global URL
    URL = URL_MAPSHIFTER if args.mapshifter else URL_QUICKMAP

    print(f"\nConverting {len(to_convert)} parish file(s) via {'Mapshifter' if args.mapshifter else 'QuickMapTools'}")
    print(f"Output: {PMTILES_OUT}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            page.goto(URL, wait_until="networkidle", timeout=60000)
            page.wait_for_load_state("domcontentloaded")
            print("Page loaded.\n")

            for parish, filename in to_convert:
                geojson_path = PARISH_DATA / filename
                if not geojson_path.exists():
                    print(f"  SKIP {parish}: {filename} not found")
                    continue

                output_name = f"parcels_{parish.replace(' ', '_').replace('.', '_')}"
                print(f"[{parish}]")
                success = convert_file(page, geojson_path, output_name)
                if not success:
                    print(f"  Failed. Continuing...")
                
                # Return to page for next file (or reload)
                if len(to_convert) > 1:
                    page.goto(URL, wait_until="networkidle", timeout=60000)
                    page.wait_for_timeout(1000)

        finally:
            browser.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
