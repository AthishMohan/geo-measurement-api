import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


DB_PATH = "geo.db"


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                status TEXT NOT NULL,
                feature_count INTEGER DEFAULT 0,
                crs TEXT,
                error TEXT,
                warnings TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS features (
                file_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                geometry_type TEXT,
                geometry TEXT,
                crs TEXT,
                properties TEXT,
                measurements TEXT,
                PRIMARY KEY (file_id, idx),
                FOREIGN KEY (file_id) REFERENCES files(id)
            );
            """
        )


def create_file(file_id, filename):
    with conn() as c:
        c.execute(
            "INSERT INTO files (id, filename, status, created_at) VALUES (?, ?, 'PROCESSING', ?)",
            (file_id, filename, datetime.now(timezone.utc).isoformat()),
        )


def save_result(file_id, crs, warnings, features):
    with conn() as c:
        c.executemany(
            "INSERT INTO features VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    file_id,
                    f["index"],
                    f["geometry_type"],
                    json.dumps(f["geometry"]),
                    f["crs"],
                    json.dumps(f["properties"]),
                    json.dumps(f["measurements"]),
                )
                for f in features
            ],
        )

        c.execute(
            "UPDATE files SET status='COMPLETED', feature_count=?, crs=?, warnings=? WHERE id=?",
            (len(features), crs, json.dumps(warnings), file_id),
        )


def mark_failed(file_id, error):
    with conn() as c:
        c.execute(
            "UPDATE files SET status='FAILED', error=? WHERE id=?",
            (error, file_id),
        )


def get_file(file_id):
    with conn() as c:
        row = c.execute(
            "SELECT * FROM files WHERE id=?",
            (file_id,),
        ).fetchone()

    if row is None:
        return None

    d = dict(row)
    d["warnings"] = json.loads(d["warnings"] or "[]")
    return d


def get_features(file_id, limit, offset):
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM features WHERE file_id=? ORDER BY idx LIMIT ? OFFSET ?",
            (file_id, limit, offset),
        ).fetchall()

    return [
        {
            "index": r["idx"],
            "geometry_type": r["geometry_type"],
            "geometry": json.loads(r["geometry"]),
            "crs": r["crs"],
            "properties": json.loads(r["properties"]),
            "measurements": json.loads(r["measurements"]),
        }
        for r in rows
    ]


def get_all_measurements(file_id):
    with conn() as c:
        rows = c.execute(
            "SELECT measurements FROM features WHERE file_id=?",
            (file_id,),
        ).fetchall()

    return [json.loads(r["measurements"]) for r in rows]