"""
eLandJamaica Parcel Sweep — v3
==============================
Extracts parcels from the public GIS portal. Default: full island extraction.
Uses pagination (resultOffset) to handle the 2000-record cap.
Streams to file to handle ~1M parcels without memory issues.

Usage:
    python eland_sweep_v3.py              # full island (~1M parcels, ~5 min)
    python eland_sweep_v3.py --parish "St. Catherine"
"""

import argparse
import io
import json
import sys
import time
from pathlib import Path

import requests
from tqdm import tqdm

BASE    = "https://gisportal.nla.gov.jm/nlagis/rest/services/ElandjamaicaAug162024/MapServer/16"
MAX_REC = 2000

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0"})


def ensure_utf8():
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def build_where(parish: str | None) -> str:
    if not parish:
        return "1=1"
    # Normalize: data uses "ST. CATHERINE" etc.
    p = parish.strip().upper().replace("'", "''")
    return f"PARISH = '{p}'"


def get_count(where: str) -> int:
    r = s.get(f"{BASE}/query", params={
        "where": where,
        "returnCountOnly": "true",
        "f": "json",
    }, timeout=60)
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("count", 0)


def fetch_page(where: str, offset: int, count: int) -> list:
    r = s.get(f"{BASE}/query", params={
        "where": where,
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": 4326,
        "resultOffset": offset,
        "resultRecordCount": count,
        "f": "json",
    }, timeout=60)
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("features", [])


def arcgis_to_geojson_geometry(geom: dict | None) -> dict | None:
    """Convert ArcGIS REST geometry to GeoJSON geometry."""
    if not geom:
        return None
    # Polygon: rings → type + coordinates
    if "rings" in geom:
        rings = geom["rings"]
        if not rings:
            return None
        return {"type": "Polygon", "coordinates": rings}
    # Polyline: paths → LineString or MultiLineString
    if "paths" in geom:
        paths = geom["paths"]
        if not paths:
            return None
        if len(paths) == 1:
            return {"type": "LineString", "coordinates": paths[0]}
        return {"type": "MultiLineString", "coordinates": paths}
    # Point: x,y → coordinates
    if "x" in geom and "y" in geom:
        return {"type": "Point", "coordinates": [geom["x"], geom["y"]]}
    return None


def feature_to_geojson_feature(f: dict) -> dict | None:
    geom = arcgis_to_geojson_geometry(f.get("geometry"))
    if geom is None:
        return None
    return {
        "type": "Feature",
        "properties": f.get("attributes", {}),
        "geometry": geom,
    }


def main():
    ensure_utf8()
    parser = argparse.ArgumentParser(description="eLandJamaica parcel sweep")
    parser.add_argument("--parish", help="Filter by parish (omit for full island)")
    parser.add_argument("-o", "--output", help="Output GeoJSON path")
    parser.add_argument("--delay", type=float, default=0.1, help="Delay between requests (seconds)")
    args = parser.parse_args()

    where = build_where(args.parish)
    parish_label = (args.parish or "all").replace(" ", "_").replace(".", "_")

    print(f"\n{'='*60}")
    print(f"  eLandJamaica Parcel Sweep — v3")
    print(f"{'='*60}")
    print(f"  Mode: {'full island' if not args.parish else f'parish={args.parish}'}")
    print(f"  WHERE: {where}")

    total = get_count(where)
    print(f"  Total parcels: {total:,}")

    if total == 0:
        print("  No parcels found. Exiting.")
        return

    out_path = args.output or f"parcels_{parish_label}.geojson"
    written = 0

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write('{"type":"FeatureCollection","features":[')
        first = True

        with tqdm(total=total, unit="parcels", desc="Fetching") as pbar:
            offset = 0
            while offset < total:
                batch = min(MAX_REC, total - offset)
                features = fetch_page(where, offset, batch)
                for feat in features:
                    gj = feature_to_geojson_feature(feat)
                    if gj is None:
                        continue
                    if not first:
                        fh.write(",")
                    fh.write(json.dumps(gj, ensure_ascii=False))
                    first = False
                    written += 1
                pbar.update(len(features))
                offset += batch
                if offset < total:
                    time.sleep(args.delay)

        fh.write("]}")

    print(f"\n  ✓ Wrote {written:,} parcels to {out_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
