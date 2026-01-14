# bot/db.py
import os
import sqlite3
from contextlib import contextmanager
from typing import Optional

from bot.config import DB_PATH

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_string TEXT UNIQUE NOT NULL,
          phone TEXT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          status TEXT DEFAULT 'active'
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS links (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          link TEXT UNIQUE NOT NULL,
          source_channel TEXT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
          link_id INTEGER UNIQUE NOT NULL,
          session_id INTEGER NOT NULL,
          assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          join_status TEXT DEFAULT 'pending',
          join_attempts INTEGER DEFAULT 0,
          last_error TEXT,
          joined_at TIMESTAMP,
          PRIMARY KEY(link_id),
          FOREIGN KEY(link_id) REFERENCES links(id),
          FOREIGN KEY(session_id) REFERENCES sessions(id)
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS join_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id INTEGER,
          link TEXT,
          status TEXT,
          error_message TEXT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        conn.commit()


# ---------------- sessions ----------------
def add_session(session_string: str, phone: str = "") -> bool:
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO sessions(session_string, phone) VALUES(?,?)",
                (session_string.strip(), phone.strip())
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

def list_sessions():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT id, session_string, phone, created_at
                       FROM sessions WHERE status='active'
                       ORDER BY id ASC""")
        return cur.fetchall()

def delete_session(session_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        conn.commit()

def get_session_by_id(session_id: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT id, session_string, phone, created_at
                       FROM sessions WHERE id=?""", (session_id,))
        return cur.fetchone()


# ---------------- links ----------------
def add_links(links: list[str], source_channel: str) -> int:
    added = 0
    with get_conn() as conn:
        cur = conn.cursor()
        for link in links:
            link = link.strip()
            if not link:
                continue
            cur.execute(
                "INSERT OR IGNORE INTO links(link, source_channel) VALUES(?,?)",
                (link, source_channel)
            )
            if cur.rowcount > 0:
                added += 1
        conn.commit()
    return added

def count_links_total() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]

def count_links_unassigned() -> int:
    with get_conn() as conn:
        return conn.execute("""
            SELECT COUNT(*)
            FROM links l
            LEFT JOIN assignments a ON a.link_id = l.id
            WHERE a.link_id IS NULL
        """).fetchone()[0]


# ---------------- assignments ----------------
def assign_unassigned_links(session_id: int, limit: int) -> int:
    """
    Assign up to `limit` unassigned links to this session.
    Returns assigned count.
    """
    with get_conn() as conn:
        cur = conn.cursor()

        # fetch unassigned link ids
        cur.execute("""
            SELECT l.id
            FROM links l
            LEFT JOIN assignments a ON a.link_id = l.id
            WHERE a.link_id IS NULL
            ORDER BY l.id ASC
            LIMIT ?
        """, (limit,))
        rows = cur.fetchall()
        if not rows:
            return 0

        assigned = 0
        for (link_id,) in rows:
            cur.execute("""
                INSERT OR IGNORE INTO assignments(link_id, session_id)
                VALUES(?,?)
            """, (link_id, session_id))
            if cur.rowcount > 0:
                assigned += 1

        conn.commit()
        return assigned

def get_pending_links_for_session(session_id: int, limit: int = 1000):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT l.id, l.link
            FROM links l
            JOIN assignments a ON a.link_id = l.id
            WHERE a.session_id = ?
              AND a.join_status = 'pending'
            ORDER BY l.id ASC
            LIMIT ?
        """, (session_id, limit))
        return cur.fetchall()

def mark_join_success(session_id: int, link_id: int):
    with get_conn() as conn:
        conn.execute("""
            UPDATE assignments
            SET join_status='success',
                joined_at=CURRENT_TIMESTAMP
            WHERE session_id=? AND link_id=?
        """, (session_id, link_id))
        conn.commit()

def mark_join_failed(session_id: int, link_id: int, error: str):
    with get_conn() as conn:
        conn.execute("""
            UPDATE assignments
            SET join_status='failed',
                join_attempts=join_attempts+1,
                last_error=?
            WHERE session_id=? AND link_id=?
        """, (error[:1000], session_id, link_id))
        conn.commit()

def log_join(session_id: int, link: str, status: str, error_message: str = ""):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO join_log(session_id, link, status, error_message)
            VALUES(?,?,?,?)
        """, (session_id, link, status, error_message[:1000]))
        conn.commit()

def get_stats():
    with get_conn() as conn:
        cur = conn.cursor()

        sessions = cur.execute("SELECT COUNT(*) FROM sessions WHERE status='active'").fetchone()[0]
        total_links = cur.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        unassigned = cur.execute("""
            SELECT COUNT(*)
            FROM links l
            LEFT JOIN assignments a ON a.link_id = l.id
            WHERE a.link_id IS NULL
        """).fetchone()[0]

        assigned = total_links - unassigned

        pending = cur.execute("SELECT COUNT(*) FROM assignments WHERE join_status='pending'").fetchone()[0]
        success = cur.execute("SELECT COUNT(*) FROM assignments WHERE join_status='success'").fetchone()[0]
        failed = cur.execute("SELECT COUNT(*) FROM assignments WHERE join_status='failed'").fetchone()[0]

        return {
            "sessions": sessions,
            "total_links": total_links,
            "assigned": assigned,
            "unassigned": unassigned,
            "pending": pending,
            "success": success,
            "failed": failed,
        }
