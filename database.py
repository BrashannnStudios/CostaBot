"""
Capa de base de datos asíncrona con aiosqlite.
Todas las operaciones son thread-safe y parametrizadas.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import aiosqlite

DB_PATH = "bot_data.db"


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_configs (
                guild_id INTEGER PRIMARY KEY,
                welcome_enabled INTEGER DEFAULT 0,
                welcome_channel_id INTEGER,
                welcome_message TEXT DEFAULT '¡Bienvenido {user} al servidor!',
                welcome_color TEXT DEFAULT '#5865F2',
                welcome_image TEXT,
                welcome_footer TEXT DEFAULT 'Miembro #{member-count} • {fecha}',
                welcome_recommended TEXT DEFAULT '[]',
                automod_enabled INTEGER DEFAULT 0,
                automod_log_channel INTEGER,
                automod_flood_count INTEGER DEFAULT 4,
                automod_flood_seconds INTEGER DEFAULT 5,
                verified_role_id INTEGER,
                unverified_role_id INTEGER,
                verify_channel_id INTEGER,
                verify_message TEXT DEFAULT 'Haz clic en el botón para verificarte con tu cuenta de Roblox.',
                verify_color TEXT DEFAULT '#57F287',
                verify_min_days INTEGER DEFAULT 3
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_warnings_guild_user
            ON warnings (guild_id, user_id)
        """)
        await db.commit()


async def get_guild_config(guild_id: int) -> dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM guild_configs WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                # Crear config por defecto
                await db.execute(
                    "INSERT INTO guild_configs (guild_id) VALUES (?)", (guild_id,)
                )
                await db.commit()
                async with db.execute(
                    "SELECT * FROM guild_configs WHERE guild_id = ?", (guild_id,)
                ) as cursor2:
                    row = await cursor2.fetchone()

            data = dict(row)
            # Parsear recommended channels
            try:
                data["welcome_recommended"] = json.loads(data["welcome_recommended"] or "[]")
            except (json.JSONDecodeError, TypeError):
                data["welcome_recommended"] = []
            return data


async def update_guild_config(guild_id: int, **kwargs: Any) -> None:
    if not kwargs:
        return

    # Serializar lista de canales recomendados
    if "welcome_recommended" in kwargs and isinstance(kwargs["welcome_recommended"], list):
        kwargs["welcome_recommended"] = json.dumps(kwargs["welcome_recommended"])

    columns = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [guild_id]

    async with aiosqlite.connect(DB_PATH) as db:
        # Asegurar que exista la fila
        await db.execute(
            "INSERT OR IGNORE INTO guild_configs (guild_id) VALUES (?)", (guild_id,)
        )
        await db.execute(
            f"UPDATE guild_configs SET {columns} WHERE guild_id = ?", values
        )
        await db.commit()


async def add_warning(
    guild_id: int, user_id: int, moderator_id: int, reason: str
) -> int:
    """Devuelve el total de warns del usuario después de añadir este."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO warnings (guild_id, user_id, moderator_id, reason, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, moderator_id, reason, time.time()),
        )
        await db.commit()

        async with db.execute(
            "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 1


async def get_warnings(guild_id: int, user_id: int) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, moderator_id, reason, timestamp
            FROM warnings
            WHERE guild_id = ? AND user_id = ?
            ORDER BY timestamp DESC
            """,
            (guild_id, user_id),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def clear_warnings(guild_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await db.commit()
        return cursor.rowcount
