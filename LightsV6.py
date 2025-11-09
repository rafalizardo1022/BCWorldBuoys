#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NOAA Light List CSV → Bridge Command Buoy.ini & Light.ini
---------------------------------------------------------
Compatible with CSV headers:
LLNR, Name, Position, Characteristic, Height, Range, Structure, Remarks
"""

import csv, re, os
from pathlib import Path

# ========== CONFIG (change for your region) ==========
INPUT_FILE = Path(r"C:\Users\Rafa\Documents\GitHub\bc-world\GMRT_OSM_Importer\Buoy creater\Discrict1.csv")
OUTPUT_DIR = Path(r"C:\Users\Rafa\Documents\GitHub\bc-world\GMRT_OSM_Importer\Buoy creater\output")

# Example: New Jersey / NYC area — change to your own
MIN_LAT, MAX_LAT = 40.344242, 40.729152
MIN_LON, MAX_LON = -74.361237, -73.883331

DEFAULT_HEIGHT_M = 5
DEFAULT_RANGE_NM = 5
DEFAULT_PERIOD_S = 4

# ========== FUNCTIONS ==========

def dms_to_decimal(dms: str):
    """Convert DMS like 39-37-06.000N to decimal degrees."""
    m = re.match(r"(\d+)[^\d]+(\d+)[^\d]+(\d+(?:\.\d+)?)([NSEW])", dms.strip(), re.I)
    if not m:
        return None
    d, mnt, s, hemi = m.groups()
    val = float(d) + float(mnt)/60 + float(s)/3600
    if hemi.upper() in ("S","W"):
        val = -val
    return val

def parse_latlon(pos: str):
    """Parse Position column like '39-37-06.000N, 072-38-40.000W'"""
    parts = re.split(r"[,/ ]+", pos.strip())
    if len(parts) < 2:
        return None, None
    lat = dms_to_decimal(parts[0])
    lon = dms_to_decimal(parts[1])
    return lat, lon

def infer_buoy_type(char, struct):
    """Decide Bridge Command buoy Type()"""
    text = f"{char or ''} {struct or ''}".upper()

    if "CARDINAL" in text:
        for d in ["NORTH","EAST","SOUTH","WEST"]:
            if d in text:
                return f"{d.lower()}_small"
        return "north_small"

    if any(k in text for k in ["MO(A)", "MORSE (A)", "R/W", "RW"]):
        return "safe"

    if "ISOLATED" in text or "DANGER" in text or "(2)" in text:
        return "black" if os.path.isdir("black") else "special_post"

    if any(k in text for k in ["YELLOW","AMBER","RESEARCH","CABLE","OBSTRUCTION","TEMP","ANCHOR"]):
        return "special_small"

    if "RG" in text or "R/G" in text or "RED AND GREEN" in text or "RED OVER GREEN" in text:
        return "pref_stbd_small"
    if "GR" in text or "G/R" in text or "GREEN AND RED" in text or "GREEN OVER RED" in text:
        return "pref_port_small"

    if "R NUN" in text or ("RED" in text and "NUN" in text):
        return "stbd_post"
    if "G CAN" in text or ("GREEN" in text and "CAN" in text):
        return "port_post"

    if "RED" in text:
        return "stbd_small"
    if "GREEN" in text:
        return "port_small"

    if "MOOR" in text or "ANCHOR" in text:
        return "mooring"

    return "other"

def extract_color(txt):
    t = (txt or "").upper()
    if "RED" in t: return "red"
    if "GREEN" in t: return "green"
    if "YELLOW" in t or "AMBER" in t: return "yellow"
    return "white"

def extract_period_seconds(txt, default=DEFAULT_PERIOD_S):
    m = re.search(r"(\d+(?:\.\d+)?)\s*s", txt or "", re.I)
    return float(m.group(1)) if m else default

def extract_range_nm(txt, default=DEFAULT_RANGE_NM):
    m = re.search(r"(\d+(?:\.\d+)?)", txt or "", re.I)
    return float(m.group(1)) if m else default

def extract_height_m(txt, default=DEFAULT_HEIGHT_M):
    try: return float(txt)
    except: return default

def sequence(ch, period):
    ticks = max(4, min(80, int(round(period / 0.25))))
    up = (ch or "").upper()
    if "FL" in up:
        on = max(1, int(round(0.5 / 0.25)))
        return "L"*on + "D"*(ticks-on)
    if "ISO" in up:
        return "L"*(ticks//2) + "D"*(ticks - ticks//2)
    if "OC" in up:
        on = int(round(ticks*0.6))
        return "L"*(on) + "D"*(ticks-on)
    return "L"

# ========== MAIN ==========

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    inside = []

    with open(INPUT_FILE, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pos = row.get("Position", "")
            lat, lon = parse_latlon(pos)
            if lat is None or lon is None:
                continue
            if not (MIN_LAT <= lat <= MAX_LAT and MIN_LON <= lon <= MAX_LON):
                continue

            name = row.get("Name", "")
            char = row.get("Characteristic", "")
            height = extract_height_m(row.get("Height", ""))
            rng = extract_range_nm(row.get("Range", ""))
            struct = row.get("Structure", "")

            buoy_type = infer_buoy_type(char, struct)
            color = extract_color(char + " " + struct)
            period = extract_period_seconds(char)
            seq = sequence(char, period)
            inside.append({
                "name": name, "lat": lat, "lon": lon,
                "type": buoy_type, "color": color,
                "height": height, "range": rng, "seq": seq
            })

    print(f"✅ Found {len(inside)} buoys within area.")
    if not inside:
        print("⚠️ No buoys found — check your MIN/MAX LAT/LON or file district.")
        return

    # ----------- Write Buoy.ini -----------
    bpath = OUTPUT_DIR / "Buoy.ini"
    with open(bpath, "w", encoding="utf-8") as f:
        f.write(f"Number={len(inside)}\n\n")
        for i, b in enumerate(inside, 1):
            f.write(f'Type({i})="{b["type"]}"\n')
            f.write(f"Long({i})={b['lon']:.6f}\nLat({i})={b['lat']:.6f}\n\n")
    print("💾 Wrote", bpath)

    # ----------- Write Light.ini -----------
    color_map = {
        "red": (255, 0, 0),
        "green": (0, 255, 0),
        "yellow": (255, 255, 0),
        "white": (255, 255, 255),
    }

    lpath = OUTPUT_DIR / "Light.ini"
    with open(lpath, "w", encoding="utf-8") as f:
        f.write(f"Number={len(inside)}\n\n")
        for i, b in enumerate(inside, 1):
            r, g, bl = color_map.get(b["color"], (255, 255, 255))
            f.write(f"Buoy({i})={i}\n")
            f.write(f"Height({i})={b['height']}\n")
            f.write(f"Red({i})={r}\nGreen({i})={g}\nBlue({i})={bl}\n")
            f.write(f"Range({i})={b['range']}\n")
            f.write(f'Sequence({i})="{b["seq"]}"\n')
            f.write("StartAngle({i})=0\nEndAngle({i})=360\nFloating({i})=1\n\n")
    print("💾 Wrote", lpath)

if __name__ == "__main__":
    main()


