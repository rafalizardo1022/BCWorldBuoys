#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NOAA / USCG Light List (CSV) → Bridge Command Buoy.ini + Light.ini
Rafael — ready-to-run Windows-safe version.
"""

from __future__ import annotations
import re, math
from pathlib import Path
import pandas as pd

# ==========================================================
# 🔧 CONFIGURATION  (edit only this section)
# ==========================================================

# 👇 Full path to your Light List CSV file
CSV_INPUTS = [
    Path(r"C:\Users\Rafa\Documents\GitHub\bc-world\GMRT_OSM_Importer\Buoy creater\Light List for District 1.csv")
]

# Dominican Republic / Caribbean bounding box
MIN_LON, MIN_LAT = -74.36, 40.35
MAX_LON, MAX_LAT = -73.88, 40.73

# Output files
OUTPUT_DIR = Path(r"C:\Users\Rafa\Documents\GitHub\bc-world\GMRT_OSM_Importer\Buoy creater\output")
BUOY_OUT  = OUTPUT_DIR / "Buoy.ini"
LIGHT_OUT = OUTPUT_DIR / "Light.ini"

DEFAULT_PERIOD_S  = 4.0
DEFAULT_RANGE_NM  = 6.0
DEFAULT_HEIGHT_M  = 12.0

LIGHT_COLOR_RGB = {
    "white": (255,255,255),
    "red":   (255,0,0),
    "green": (0,255,0),
    "yellow":(255,255,0),
    "blue":  (0,0,255),
}

# ==========================================================
# ⚙️ FUNCTIONS
# ==========================================================

def in_bbox(lon, lat):
    return MIN_LON <= lon <= MAX_LON and MIN_LAT <= lat <= MAX_LAT

def dms_to_decimal(dms: str) -> float | None:
    """Convert '18°26'48"N' or '69°52'19"W' to decimal degrees."""
    if not dms:
        return None
    dms = dms.strip().replace("º","°")
    m = re.match(r"(\d+)[°\s]+(\d+)[\'\s]+(\d+(?:\.\d+)?)[\"\s]*([NSEW])", dms)
    if not m:
        return None
    deg, minutes, seconds, hemi = m.groups()
    val = float(deg) + float(minutes)/60 + float(seconds)/3600
    if hemi in ("S","W"): val = -val
    return val

def parse_lat_lon(lat_raw, lon_raw):
    lat = dms_to_decimal(lat_raw)
    lon = dms_to_decimal(lon_raw)
    if lat is None or lon is None:
        return None
    return lon, lat

def extract_color(txt: str) -> str:
    txt = txt.lower()
    for c in LIGHT_COLOR_RGB.keys():
        if c in txt: return c
    if "w" in txt: return "white"
    if "r" in txt: return "red"
    if "g" in txt: return "green"
    if "y" in txt: return "yellow"
    if "b" in txt: return "blue"
    return "white"

def extract_period_seconds(txt: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*s", txt, re.I)
    return float(m.group(1)) if m else DEFAULT_PERIOD_S

def extract_range_nm(txt: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*M\b", txt)
    return float(m.group(1)) if m else DEFAULT_RANGE_NM

def extract_char(txt: str) -> str:
    t = txt.lower()
    for key in ["iso","oc","fl","q","vq"]:
        if key in t:
            return key.upper()
    return "FIX"

def sequence(ch, period_s):
    """Bridge Command light sequence string (L/D pattern)."""
    P = period_s if period_s > 0.5 else DEFAULT_PERIOD_S
    ticks = int(round(P / 0.25))
    if ch.startswith("FL"): return "L"*2 + "D"*(ticks-2)
    if ch.startswith("ISO"): return "L"*(ticks//2) + "D"*(ticks//2)
    if ch.startswith("OC"): return "L"*(int(ticks*0.6)) + "D"*(int(ticks*0.4))
    if ch in ("Q","VQ"): return "LD"* (ticks//2)
    return "L"

# ==========================================================
# 🚀 MAIN
# ==========================================================

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for path in CSV_INPUTS:
        if path.exists():
            df = pd.read_csv(path, dtype=str, on_bad_lines="skip", encoding="utf-8")
            frames.append(df)
        else:
            print(f"[WARN] File not found: {path}")
    if not frames:
        print("[ERROR] No CSV files found.")
        return

    df = pd.concat(frames, ignore_index=True)
    df.fillna("", inplace=True)

    col_lat = next((c for c in df.columns if "lat" in c.lower()), None)
    col_lon = next((c for c in df.columns if "lon" in c.lower() or "long" in c.lower()), None)
    col_char = next((c for c in df.columns if "char" in c.lower()), None)
    col_name = next((c for c in df.columns if "name" in c.lower()), None)

    buoys, lights = [], []

    for _, row in df.iterrows():
        lat_raw = row.get(col_lat, "")
        lon_raw = row.get(col_lon, "")
        pos = parse_lat_lon(lat_raw, lon_raw)
        if not pos: continue
        lon, lat = pos
        if not in_bbox(lon, lat): continue

        txt = row.get(col_char, "")
        color = extract_color(txt)
        period = extract_period_seconds(txt)
        rng = extract_range_nm(txt)
        ch = extract_char(txt)
        seq = sequence(ch, period)
        name = row.get(col_name, "").strip() or "Unnamed Light"

        buoys.append({
            "type":"Special",
            "lon":lon,
            "lat":lat,
            "name":name
        })
        lights.append({
            "rgb":LIGHT_COLOR_RGB.get(color,(255,255,255)),
            "range":rng,
            "seq":seq
        })

    # Write Buoy.ini
    lines = [f"Number={len(buoys)}\n"]
    for i,b in enumerate(buoys, start=1):
        lines.append(f'Type({i})="{b["type"]}"\n')
        lines.append(f"Long({i})={b['lon']:.8f}\n")
        lines.append(f"Lat({i})={b['lat']:.8f}\n\n")
    BUOY_OUT.write_text("".join(lines), encoding="utf-8")

    # Write Light.ini
    lines = [f"Number={len(lights)}\n\n"]
    for i,l in enumerate(lights, start=1):
        r,g,b = l["rgb"]
        lines.append(f"Buoy({i})={i}\n")
        lines.append(f"Height({i})={DEFAULT_HEIGHT_M}\n")
        lines.append(f"Red({i})={r}\nGreen({i})={g}\nBlue({i})={b}\n")
        lines.append(f"Range({i})={l['range']}\n")
        lines.append(f'Sequence({i})="{l["seq"]}"\n')
        lines.append(f"StartAngle({i})=0\nEndAngle({i})=360\nFloating({i})=1\n\n")
    LIGHT_OUT.write_text("".join(lines), encoding="utf-8")

    print(f"✅ Created {BUOY_OUT} and {LIGHT_OUT} with {len(buoys)} entries.")

if __name__ == "__main__":
    main()
