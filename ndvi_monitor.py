"""
Forest Carbon Monitor — NDVI Land Cover Change Detector
Author: Nanthakumar P
Area:   Bandipur-Nagarhole Forest Zone, Karnataka, India
Data:   Sentinel-2 L2A (NIR Band 8, Red Band 4)
"""

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import json, os, argparse
from datetime import date

# ── Paths ──────────────────────────────────────────────────────────────────
DATA = "data"
OUT  = "output"
os.makedirs(DATA, exist_ok=True)
os.makedirs(OUT,  exist_ok=True)

# ── Step 1: Load or generate satellite bands ────────────────────────────────
def generate_sample_data():
    """
    Generates realistic Sentinel-2-like GeoTIFF bands for Karnataka.
    Replace this with real sentinelsat / Copernicus downloads for production.
    Covers: Bandipur-Nagarhole (11.6-12.1N, 76.0-76.6E)
    """
    west, south, east, north = 76.0, 11.6, 76.6, 12.1
    width, height = 512, 512
    transform = from_bounds(west, south, east, north, width, height)
    crs = CRS.from_epsg(4326)

    def make_scene(seed, forest_frac=0.6, degrade_frac=0.15):
        rng = np.random.default_rng(seed)
        base = rng.random((height, width))
        forest   = base < forest_frac
        degraded = (base >= forest_frac) & (base < forest_frac + degrade_frac)
        agri     = (base >= forest_frac + degrade_frac) & (base < forest_frac + degrade_frac + 0.15)
        bare     = ~(forest | degraded | agri)
        nir = np.zeros((height, width), dtype=np.float32)
        red = np.zeros((height, width), dtype=np.float32)
        nir[forest]   = rng.normal(6500, 400, forest.sum()).clip(4000, 8500)
        red[forest]   = rng.normal(800,  150, forest.sum()).clip(400,  1500)
        nir[degraded] = rng.normal(4000, 500, degraded.sum()).clip(2000, 6000)
        red[degraded] = rng.normal(1800, 300, degraded.sum()).clip(800,  3000)
        nir[agri]     = rng.normal(3500, 600, agri.sum()).clip(1500, 5500)
        red[agri]     = rng.normal(1200, 200, agri.sum()).clip(600,  2500)
        nir[bare]     = rng.normal(2000, 400, bare.sum()).clip(800,  3500)
        red[bare]     = rng.normal(2200, 400, bare.sum()).clip(1000, 4000)
        return nir, red, transform, crs

    def save(arr, path, transform, crs):
        meta = dict(driver='GTiff', height=arr.shape[0], width=arr.shape[1],
                    count=1, dtype=arr.dtype, crs=crs, transform=transform)
        with rasterio.open(path, 'w', **meta) as dst:
            dst.write(arr, 1)

    print("Generating baseline scene (2022)...")
    nir22, red22, t, c = make_scene(2022, forest_frac=0.65, degrade_frac=0.10)
    save(nir22, f"{DATA}/NIR_2022.tif", t, c)
    save(red22, f"{DATA}/RED_2022.tif", t, c)

    print("Generating monitoring scene (2024)...")
    nir24, red24, t, c = make_scene(2024, forest_frac=0.55, degrade_frac=0.18)
    save(nir24, f"{DATA}/NIR_2024.tif", t, c)
    save(red24, f"{DATA}/RED_2024.tif", t, c)
    print("Sample data ready.\n")

# ── Step 2: Compute NDVI ────────────────────────────────────────────────────
def compute_ndvi(nir_path, red_path):
    with rasterio.open(nir_path) as f:
        nir  = f.read(1).astype(np.float32)
        meta = f.meta.copy()
    with rasterio.open(red_path) as f:
        red = f.read(1).astype(np.float32)
    with np.errstate(divide='ignore', invalid='ignore'):
        ndvi = np.where((nir + red) == 0, 0, (nir - red) / (nir + red))
    return np.clip(ndvi, -1, 1), meta

# ── Step 3: Classify land cover ─────────────────────────────────────────────
def classify(ndvi_arr):
    cls = np.zeros_like(ndvi_arr, dtype=np.uint8)
    cls[ndvi_arr > 0.45]                        = 3  # Dense forest
    cls[(ndvi_arr > 0.25) & (ndvi_arr <= 0.45)] = 2  # Sparse vegetation
    cls[(ndvi_arr > 0.05) & (ndvi_arr <= 0.25)] = 1  # Agriculture
    cls[ndvi_arr <= 0.05]                        = 0  # Bare / built-up
    return cls

# ── Step 4: Compute area stats ──────────────────────────────────────────────
def area_stats(cls, label, px_ha=0.36):
    return {
        "period":           label,
        "dense_forest_ha":  round(float((cls == 3).sum() * px_ha), 1),
        "sparse_veg_ha":    round(float((cls == 2).sum() * px_ha), 1),
        "agriculture_ha":   round(float((cls == 1).sum() * px_ha), 1),
        "bare_ha":          round(float((cls == 0).sum() * px_ha), 1),
    }

# ── Step 5: Generate maps ───────────────────────────────────────────────────
def generate_maps(ndvi22, ndvi24, change, s22, s24, loss_ha, loss_pct):
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.patch.set_facecolor('#0f1117')
    for ax in axes:
        ax.set_facecolor('#0f1117')
        ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values(): sp.set_color('#333')

    for arr, ax, title in [
        (ndvi22, axes[0], "NDVI — 2022 (Baseline)"),
        (ndvi24, axes[1], "NDVI — 2024 (Monitoring)"),
        (change, axes[2], "NDVI Change (2022 → 2024)"),
    ]:
        vmin, vmax = (-0.4, 0.4) if "Change" in title else (-0.1, 0.8)
        im = ax.imshow(arr, cmap=plt.cm.RdYlGn, vmin=vmin, vmax=vmax)
        ax.set_title(title, color='white', fontsize=11, pad=8)
        cb = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cb.ax.yaxis.set_tick_params(color='white', labelcolor='white')

    axes[1].set_xlabel("Bandipur–Nagarhole, Karnataka (76.0–76.6°E, 11.6–12.1°N)",
                       color='#aaa', fontsize=8)
    plt.tight_layout()
    plt.savefig(f"{OUT}/ndvi_analysis_map.png", dpi=150, bbox_inches='tight',
                facecolor='#0f1117')
    plt.close()

    # Bar chart
    fig2, ax = plt.subplots(figsize=(8, 4))
    fig2.patch.set_facecolor('#0f1117')
    ax.set_facecolor('#0f1117')
    cats = ["Dense forest", "Sparse veg", "Agriculture", "Bare"]
    keys = ["dense_forest_ha", "sparse_veg_ha", "agriculture_ha", "bare_ha"]
    x = np.arange(len(cats)); w = 0.35
    ax.bar(x - w/2, [s22[k] for k in keys], w, label='2022', color='#1D9E75', alpha=0.85)
    ax.bar(x + w/2, [s24[k] for k in keys], w, label='2024', color='#D85A30', alpha=0.85)
    ax.set_xticks(x); ax.set_xticklabels(cats, color='white', fontsize=9)
    ax.tick_params(colors='white')
    ax.set_ylabel("Area (hectares)", color='white')
    ax.legend(facecolor='#1a1a2e', labelcolor='white', edgecolor='#333')
    ax.set_title(f"Land Cover Change  |  Forest loss: {loss_ha} ha ({loss_pct}%)",
                 color='white', fontsize=11)
    for sp in ax.spines.values(): sp.set_color('#333')
    plt.tight_layout()
    plt.savefig(f"{OUT}/land_cover_chart.png", dpi=150, bbox_inches='tight',
                facecolor='#0f1117')
    plt.close()
    print("Maps saved.")

# ── Main ────────────────────────────────────────────────────────────────────
def main():
    if not os.path.exists(f"{DATA}/NIR_2022.tif"):
        generate_sample_data()

    print("Computing NDVI...")
    ndvi22, meta = compute_ndvi(f"{DATA}/NIR_2022.tif", f"{DATA}/RED_2022.tif")
    ndvi24, _    = compute_ndvi(f"{DATA}/NIR_2024.tif", f"{DATA}/RED_2024.tif")
    change = ndvi24 - ndvi22

    print("Classifying land cover...")
    cls22 = classify(ndvi22)
    cls24 = classify(ndvi24)

    s22 = area_stats(cls22, "2022")
    s24 = area_stats(cls24, "2024")
    loss_ha  = round(s22["dense_forest_ha"] - s24["dense_forest_ha"], 1)
    loss_pct = round(loss_ha / s22["dense_forest_ha"] * 100, 1)

    print(f"\nForest loss: {loss_ha} ha ({loss_pct}%)")

    # Save GeoTIFFs
    meta.update(dtype='float32')
    for arr, name in [(ndvi22,"ndvi_2022"), (ndvi24,"ndvi_2024"), (change,"ndvi_change")]:
        with rasterio.open(f"{OUT}/{name}.tif", 'w', **meta) as dst:
            dst.write(arr, 1)
    cls_meta = meta.copy(); cls_meta.update(dtype='uint8')
    for arr, name in [(cls22,"classified_2022"), (cls24,"classified_2024")]:
        with rasterio.open(f"{OUT}/{name}.tif", 'w', **cls_meta) as dst:
            dst.write(arr, 1)

    stats = {"2022": s22, "2024": s24, "forest_loss_ha": loss_ha,
             "forest_loss_pct": loss_pct,
             "ndvi_mean_2022": round(float(ndvi22.mean()), 3),
             "ndvi_mean_2024": round(float(ndvi24.mean()), 3)}
    with open(f"{OUT}/stats.json", "w") as f:
        json.dump(stats, f, indent=2)

    print("Generating maps...")
    generate_maps(ndvi22, ndvi24, change, s22, s24, loss_ha, loss_pct)
    print("\nDone. Check the output/ folder.")
    return stats

if __name__ == "__main__":
    main()
