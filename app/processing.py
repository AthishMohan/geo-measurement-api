import json
import tempfile
import zipfile
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
import shapely
from pyproj import Transformer
from shapely.geometry import mapping
from shapely.ops import transform as shp_transform

AREA_TYPES = {"Polygon", "MultiPolygon"}
LENGTH_TYPES = {"LineString", "MultiLineString"}
POINT_TYPES = {"Point", "MultiPoint"}


# ---------- CRS handling ----------
def utm_epsg(geom_wgs84) -> int:
    """Pick the UTM zone (EPSG code) that contains the geometry's centroid."""
    c = geom_wgs84.centroid
    zone = int((c.x + 180) // 6) % 60 + 1
    return (32600 if c.y >= 0 else 32700) + zone


@lru_cache(maxsize=64)
def _transformer(epsg: int) -> Transformer:
    return Transformer.from_crs(4326, epsg, always_xy=True)


# ---------- Measurement ----------
def measure(geom_wgs84) -> dict:
    """Takes a geometry in EPSG:4326 and returns a measurement dict. Never raises."""
    try:
        if geom_wgs84 is None or geom_wgs84.is_empty:
            return {"status": "skipped", "reason": "empty or missing geometry"}

        gtype = geom_wgs84.geom_type
        if gtype in POINT_TYPES:
            return {"status": "not_required"}
        if gtype not in AREA_TYPES | LENGTH_TYPES:
            return {"status": "unsupported", "reason": f"{gtype} is not supported"}

        geom = shapely.force_2d(geom_wgs84)
        epsg = utm_epsg(geom)
        projected = shp_transform(_transformer(epsg).transform, geom)

        result = {
            "status": "measured",
            "projected_crs": f"EPSG:{epsg}",
            "is_valid_geometry": bool(geom.is_valid),
        }
        if gtype in AREA_TYPES:
            result["area_sq_m"] = round(projected.area, 3)
            result["area_hectares"] = round(projected.area / 10_000, 6)
        else:
            result["length_m"] = round(projected.length, 3)
            result["length_km"] = round(projected.length / 1000, 6)
        return result
    except Exception as exc:
        return {"status": "error", "reason": str(exc)}


# ---------- File reading ----------
def _safe_extract(zip_path: Path, dest: Path):
    dest = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if not target.is_relative_to(dest):
                raise ValueError("Zip contains an unsafe file path")
        zf.extractall(dest)


def _read_kml(path: Path) -> gpd.GeoDataFrame:
    layers = pyogrio.list_layers(path)
    frames = [gpd.read_file(path, layer=str(name)) for name in layers[:, 0]]
    frames = [f for f in frames if len(f) > 0]
    if not frames:
        raise ValueError("KML contains no features")
    return gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True),
        crs=frames[0].crs
    )


def _read_shapefile_zip(path: Path) -> gpd.GeoDataFrame:
    with tempfile.TemporaryDirectory() as tmp:
        _safe_extract(path, Path(tmp))
        shps = [
            p for p in Path(tmp).rglob("*.shp")
            if "__MACOSX" not in p.parts
        ]
        if not shps:
            raise ValueError("No .shp file found inside the zip")
        return gpd.read_file(shps[0])


# ---------- Main entry ----------
def process(path: Path):
    """Returns (crs_label, warnings, features)."""
    warnings = []

    if path.suffix.lower() == ".zip":
        gdf = _read_shapefile_zip(path)
    else:
        gdf = _read_kml(path)

    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
        warnings.append(
            "No CRS found in file (missing .prj?). Assumed EPSG:4326."
        )

    epsg = gdf.crs.to_epsg()
    crs_label = f"EPSG:{epsg}" if epsg else gdf.crs.name

    gdf_wgs84 = gdf.to_crs(4326)
    geom_col = gdf.geometry.name

    props = json.loads(
        pd.DataFrame(gdf.drop(columns=geom_col)).to_json(
            orient="records",
            date_format="iso",
            default_handler=str
        )
    )

    features = []

    for i, (orig, wgs) in enumerate(
        zip(gdf.geometry, gdf_wgs84.geometry)
    ):
        features.append(
            {
                "index": i,
                "geometry_type": orig.geom_type if orig is not None else None,
                "geometry": mapping(orig) if orig is not None else None,
                "crs": crs_label,
                "properties": props[i],
                "measurements": measure(wgs),
            }
        )

    return crs_label, warnings, features