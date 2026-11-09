import aiosqlite
from datetime import datetime

DB_PATH = "bot_stats.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS links (
                chat_id INTEGER NOT NULL,
                invite_link TEXT NOT NULL,
                name TEXT,
                PRIMARY KEY (chat_id, invite_link)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                chat_id INTEGER NOT NULL,
                invite_link TEXT NOT NULL,
                join_requests INTEGER DEFAULT 0,
                joins INTEGER DEFAULT 0,
                leaves INTEGER DEFAULT 0,
                active_members INTEGER DEFAULT 0,
                PRIMARY KEY (chat_id, invite_link)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS members (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                invite_link TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                left_at TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        await db.commit()

async def save_link(chat_id: int, invite_link: str, name: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO links (chat_id, invite_link, name) VALUES (?, ?, ?)",
            (chat_id, invite_link, name)
        )
        await db.execute(
            "INSERT OR IGNORE INTO stats (chat_id, invite_link) VALUES (?, ?)",
            (chat_id, invite_link)
        )
        await db.commit()

async def get_link_for_chat(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT invite_link, name FROM links WHERE chat_id = ? LIMIT 1",
            (chat_id,)
        ) as cursor:
            return await cursor.fetchone()

async def increment_join_request(chat_id: int, invite_link: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE stats SET join_requests = join_requests + 1 WHERE chat_id = ? AND invite_link = ?",
            (chat_id, invite_link)
        )
        await db.commit()

async def register_join(chat_id: int, user_id: int, invite_link: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE stats SET joins = joins + 1, active_members = active_members + 1 WHERE chat_id = ? AND invite_link = ?",
            (chat_id, invite_link)
        )
        await db.execute("""
            INSERT INTO members (chat_id, user_id, invite_link, is_active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET is_active = 1, left_at = NULL, invite_link = excluded.invite_link
        """, (chat_id, user_id, invite_link))
        await db.commit()

async def register_leave(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT invite_link FROM members WHERE chat_id = ? AND user_id = ? AND is_active = 1",
            (chat_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return
            invite_link = row[0]

        await db.execute(
            "UPDATE stats SET leaves = leaves + 1, active_members = active_members - 1 WHERE chat_id = ? AND invite_link = ?",
            (chat_id, invite_link)
        )
        await db.execute(
            "UPDATE members SET is_active = 0, left_at = CURRENT_TIMESTAMP WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        await db.commit()

async def get_stats(chat_id: int, invite_link: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if invite_link:
            async with db.execute(
                "SELECT join_requests, joins, leaves, active_members FROM stats WHERE chat_id = ? AND invite_link = ?",
                (chat_id, invite_link)
            ) as cursor:
                return await cursor.fetchone()
        else:
            async with db.execute(
                "SELECT SUM(join_requests), SUM(joins), SUM(leaves), SUM(active_members) FROM stats WHERE chat_id = ?",
                (chat_id,)
            ) as cursor:
                return await cursor.fetchone()
