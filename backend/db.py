import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "user.db"


def init_db():
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS visited (
                place_id TEXT PRIMARY KEY,
                visited_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS wishlist (
                place_id TEXT PRIMARY KEY,
                added_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS custom_places (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS photos (
                place_id TEXT PRIMARY KEY,
                image_url TEXT,
                thumb_url TEXT,
                source TEXT,
                fetched_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS place_details (
                place_id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                fetched_at TEXT DEFAULT (datetime('now'))
            );
            """
        )


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_visited_ids() -> set[str]:
    with connect() as conn:
        rows = conn.execute("SELECT place_id FROM visited").fetchall()
        return {r["place_id"] for r in rows}


def mark_visited(place_id: str, visited: bool):
    with connect() as conn:
        if visited:
            conn.execute(
                "INSERT OR IGNORE INTO visited (place_id) VALUES (?)", (place_id,)
            )
        else:
            conn.execute("DELETE FROM visited WHERE place_id = ?", (place_id,))


def get_custom_places() -> list[dict]:
    import json
    with connect() as conn:
        rows = conn.execute("SELECT data FROM custom_places").fetchall()
        return [json.loads(r["data"]) for r in rows]


def add_custom_place(place: dict):
    import json
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO custom_places (id, data) VALUES (?, ?)",
            (place["id"], json.dumps(place)),
        )


def delete_custom_place(place_id: str):
    with connect() as conn:
        conn.execute("DELETE FROM custom_places WHERE id = ?", (place_id,))
        conn.execute("DELETE FROM visited WHERE place_id = ?", (place_id,))
        conn.execute("DELETE FROM wishlist WHERE place_id = ?", (place_id,))


def get_wishlist_ids() -> set[str]:
    with connect() as conn:
        rows = conn.execute("SELECT place_id FROM wishlist").fetchall()
        return {r["place_id"] for r in rows}


def mark_wishlist(place_id: str, on: bool):
    with connect() as conn:
        if on:
            conn.execute("INSERT OR IGNORE INTO wishlist (place_id) VALUES (?)", (place_id,))
        else:
            conn.execute("DELETE FROM wishlist WHERE place_id = ?", (place_id,))


def get_cached_photo(place_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT image_url, thumb_url, source FROM photos WHERE place_id = ?",
            (place_id,),
        ).fetchone()
        return dict(row) if row else None


def cache_photo(place_id: str, image_url: str | None, thumb_url: str | None, source: str):
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO photos (place_id, image_url, thumb_url, source, fetched_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            (place_id, image_url, thumb_url, source),
        )


def get_cached_details(place_id: str) -> dict | None:
    import json as _json
    with connect() as conn:
        row = conn.execute(
            "SELECT content FROM place_details WHERE place_id = ?", (place_id,)
        ).fetchone()
        return _json.loads(row["content"]) if row else None


def cache_details(place_id: str, content: dict):
    import json as _json
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO place_details (place_id, content, fetched_at)
               VALUES (?, ?, datetime('now'))""",
            (place_id, _json.dumps(content)),
        )
