"""Хранение заявок в SQLite."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "leads.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id       INTEGER NOT NULL,
    username    TEXT,
    full_name   TEXT,
    purpose     TEXT,
    budget      TEXT,
    timing      TEXT,
    region      TEXT,
    phone       TEXT,
    score       INTEGER,
    source_key  TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_tg ON leads(tg_id);
"""


async def init() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await migrate(db)
        await db.commit()


async def migrate(db: aiosqlite.Connection) -> None:
    """Дописываем недостающие колонки в уже существующую базу."""
    cur = await db.execute("PRAGMA table_info(leads)")
    existing = {row[1] for row in await cur.fetchall()}
    for column, ddl in (("source_key", "TEXT"),):
        if column not in existing:
            await db.execute(f"ALTER TABLE leads ADD COLUMN {column} {ddl}")


async def save_lead(
    *,
    tg_id: int,
    username: str | None,
    full_name: str,
    answers: dict[str, str],
    phone: str,
    score: int,
    source_key: str = "",
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT INTO leads
                (tg_id, username, full_name, purpose, budget, timing,
                 region, phone, score, source_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tg_id,
                username,
                full_name,
                answers.get("purpose"),
                answers.get("budget"),
                answers.get("timing"),
                answers.get("region"),
                phone,
                score,
                source_key,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        await db.commit()
        return cur.lastrowid or 0


async def all_leads() -> list[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, created_at, full_name, username, tg_id, purpose, "
            "budget, timing, region, phone, score, "
            "COALESCE(source_key, '') FROM leads ORDER BY id"
        )
        return list(await cur.fetchall())


async def count_leads() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM leads")
        row = await cur.fetchone()
        return int(row[0]) if row else 0
