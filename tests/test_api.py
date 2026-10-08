import zipfile

import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon

from app import db, main

KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>Plot A</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
77.59,12.97,0 77.60,12.97,0 77.60,12.98,0 77.59,12.98,0 77.59,12.97,0
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Road</name><LineString><coordinates>77.59,12.97,0 77.60,12.97,0</coordinates></LineString></Placemark>
<Placemark><name>Gate</name><Point><coordinates>77.595,12.975,0</coordinates></Point></Placemark>
</Document></kml>"""


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    with TestClient(main.app) as c:
        yield c


def upload(client, name, content):
    return client.post("/api/files/", files={"file": (name, content)})


def test_kml_upload_and_measurements(client):
    r = upload(client, "survey.kml", KML.encode())
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 3
    assert body["crs"] == "EPSG:4326"

    info = client.get(f"/api/files/{body['id']}/").json()
    assert info["filename"] == "survey.kml"

    m = client.get(f"/api/files/{body['id']}/measurements/").json()
    by_type = {f["geometry_type"]: f for f in m["features"]}

    assert 1.15e6 < by_type["Polygon"]["measurements"]["area_sq_m"] < 1.25e6
    assert 1000 < by_type["LineString"]["measurements"]["length_m"] < 1200
    assert by_type["Point"]["measurements"]["status"] == "not_required"
    assert by_type["Polygon"]["measurements"]["projected_crs"] == "EPSG:32643"


def test_shapefile_zip_upload(client, tmp_path):
    poly = Polygon([
        (77.59, 12.97),
        (77.60, 12.97),
        (77.60, 12.98),
        (77.59, 12.98)
    ])

    shp_dir = tmp_path / "shp"
    shp_dir.mkdir()

    gpd.GeoDataFrame(
        {"name": ["plot"]},
        geometry=[poly],
        crs="EPSG:4326"
    ).to_file(shp_dir / "plots.shp")

    zip_path = tmp_path / "plots.zip"

    with zipfile.ZipFile(zip_path, "w") as z:
        for f in shp_dir.iterdir():
            z.write(f, f.name)

    r = upload(client, "plots.zip", zip_path.read_bytes())

    assert r.json()["status"] == "COMPLETED"

    m = client.get(
        f"/api/files/{r.json()['id']}/measurements/"
    ).json()

    assert m["features"][0]["properties"]["name"] == "plot"
    assert m["summary"]["total_area_sq_m"] > 1e6


def test_rejects_unsupported_extension(client):
    assert upload(
        client,
        "notes.txt",
        b"hello"
    ).status_code == 400


def test_corrupt_zip_marked_failed(client):
    r = upload(
        client,
        "bad.zip",
        b"this is not a zip"
    )

    assert r.json()["status"] == "FAILED"

    m = client.get(
        f"/api/files/{r.json()['id']}/measurements/"
    )

    assert m.status_code == 409


def test_unknown_id_returns_404(client):
    assert client.get(
        "/api/files/doesnotexist/"
    ).status_code == 404