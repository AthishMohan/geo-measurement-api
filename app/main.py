import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from . import db, processing

UPLOAD_DIR = Path("uploads")
MAX_BYTES = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXT = {".zip", ".kml"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    UPLOAD_DIR.mkdir(exist_ok=True)
    db.init_db()
    yield


app = FastAPI(
    title="Geospatial File Measurement API",
    lifespan=lifespan
)


@app.post("/api/files/", status_code=201)
def upload_file(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()

    if ext not in ALLOWED_EXT:
        raise HTTPException(
            400,
            "Only .zip (containing a Shapefile) or .kml files are accepted"
        )

    file_id = uuid.uuid4().hex[:12]
    dest = UPLOAD_DIR / f"{file_id}{ext}"

    size, too_big = 0, False

    with dest.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)

            if size > MAX_BYTES:
                too_big = True
                break

            out.write(chunk)

    if too_big:
        dest.unlink(missing_ok=True)
        raise HTTPException(413, "File too large (max 50 MB)")

    db.create_file(file_id, file.filename)

    try:
        crs, warnings, features = processing.process(dest)
        db.save_result(file_id, crs, warnings, features)
    except Exception as exc:
        db.mark_failed(
            file_id,
            f"{type(exc).__name__}: {exc}"
        )

    return db.get_file(file_id)


@app.get("/api/files/{file_id}/")
def get_file(file_id: str):
    record = db.get_file(file_id)

    if record is None:
        raise HTTPException(404, "File not found")

    return record


@app.get("/api/files/{file_id}/measurements/")
def get_measurements(
    file_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    record = db.get_file(file_id)

    if record is None:
        raise HTTPException(404, "File not found")

    if record["status"] != "COMPLETED":
        raise HTTPException(
            409,
            f"File status is {record['status']}: {record['error']}"
        )

    all_m = db.get_all_measurements(file_id)

    summary = {
        "measured": sum(
            1 for m in all_m
            if m["status"] == "measured"
        ),
        "skipped_or_unsupported": sum(
            1 for m in all_m
            if m["status"] in ("skipped", "unsupported", "error")
        ),
        "total_area_sq_m": round(
            sum(m.get("area_sq_m", 0) for m in all_m),
            3
        ),
        "total_length_m": round(
            sum(m.get("length_m", 0) for m in all_m),
            3
        ),
    }

    return {
        "file_id": file_id,
        "crs": record["crs"],
        "total_features": record["feature_count"],
        "limit": limit,
        "offset": offset,
        "summary": summary,
        "features": db.get_features(
            file_id,
            limit,
            offset
        ),
    }