#Code to get the exact MIN and MAX LAT and LONGS of your TIF file

import rasterio

tif_path = r"C:\Users\Rafa\Documents\GitHub\bc-world\GMRT_OSM_Importer\GMRTv4_4_0_20251021topo.tif"

with rasterio.open(tif_path) as src:
    b = src.bounds
    print(f"MIN_LAT, MAX_LAT = {b.bottom:.6f}, {b.top:.6f}")
    print(f"MIN_LON, MAX_LON = {b.left:.6f}, {b.right:.6f}")

