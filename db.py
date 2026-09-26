"""
All database access lives here. SQLite, accessed synchronously — fine at this
scale (single-process bot, small number of users). If this ever needs to
scale past a few thousand active users, swap for Postgres, but the function
signatures below can stay the same.
"""
import sqlite3
import random
import string
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

from config import DB_PATH, LINK_CODE_TTL_MINUTES

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _now_utc_iso() -> str:
    """UTC timestamp as 'YYYY-MM-DDTHH:MM:SS' with no offset suffix — this
    MUST match the format SQLite's own timestamp columns use (see the
    strftime() default below), or string comparisons between the two break
    silently (space vs 'T' separator sorts wrong)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                role        TEXT NOT NULL CHECK(role IN ('elder','caregiver')),
                name        TEXT,
                timezone    TEXT DEFAULT 'UTC',
                created_at  TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
            );

            CREATE TABLE IF NOT EXISTS links (
                elder_id     INTEGER NOT NULL,
                caregiver_id INTEGER NOT NULL,
                PRIMARY KEY (elder_id, caregiver_id),
                FOREIGN KEY (elder_id) REFERENCES users(telegram_id),
                FOREIGN KEY (caregiver_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS link_codes (
                code       TEXT PRIMARY KEY,
                elder_id   INTEGER NOT NULL,
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
                expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS medications (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                elder_id    INTEGER NOT NULL,
                name        TEXT NOT NULL,
                dose        TEXT,
                times       TEXT NOT NULL,      -- comma-separated "HH:MM"
                days        TEXT NOT NULL DEFAULT 'daily',  -- 'daily' or "Mon,Wed,Fri"
                active      INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
            );

            CREATE TABLE IF NOT EXISTS logs (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                medication_id  INTEGER NOT NULL,
                scheduled_for  TEXT NOT NULL,   -- elder-local "YYYY-MM-DDTHH:MM"
                status         TEXT NOT NULL DEFAULT 'pending', -- pending/taken/skipped/missed
                created_at     TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),  -- UTC, used for escalation timing
                responded_at   TEXT,
                nudged         INTEGER NOT NULL DEFAULT 0,
                escalated      INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (medication_id) REFERENCES medications(id)
            );

            CREATE INDEX IF NOT EXISTS idx_logs_medication ON logs(medication_id);
            CREATE INDEX IF NOT EXISTS idx_logs_status ON logs(status);
            CREATE INDEX IF NOT EXISTS idx_meds_elder ON medications(elder_id);
            """
        )


# ---------------------------------------------------------------- users ----

def upsert_user(telegram_id: int, role: str = None, name: str = None, tz: str = None):
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO users (telegram_id, role, name, timezone) VALUES (?, ?, ?, ?)",
                (telegram_id, role or "elder", name, tz or "UTC"),
            )
        else:
            if role is not None:
                conn.execute("UPDATE users SET role = ? WHERE telegram_id = ?", (role, telegram_id))
            if name is not None:
                conn.execute("UPDATE users SET name = ? WHERE telegram_id = ?", (name, telegram_id))
            if tz is not None:
                conn.execute("UPDATE users SET timezone = ? WHERE telegram_id = ?", (tz, telegram_id))


def get_user(telegram_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()


# ------------------------------------------------------------ linking ----

def create_link_code(elder_id: int) -> str:
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    expires = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=LINK_CODE_TTL_MINUTES)).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO link_codes (code, elder_id, expires_at) VALUES (?, ?, ?)",
            (code, elder_id, expires),
        )
    return code


def consume_link_code(code: str, caregiver_id: int):
    """Returns the elder_id if the code was valid and unexpired, else None."""
    code = code.strip().upper()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM link_codes WHERE code = ?", (code,)
        ).fetchone()
        if row is None:
            return None
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc).replace(tzinfo=None):
            return None
        elder_id = row["elder_id"]
        conn.execute(
            "INSERT OR IGNORE INTO links (elder_id, caregiver_id) VALUES (?, ?)",
            (elder_id, caregiver_id),
        )
        conn.execute("DELETE FROM link_codes WHERE code = ?", (code,))
        return elder_id


def get_caregivers_for_elder(elder_id: int):
    with get_conn() as conn:
        return conn.execute(
            """SELECT u.* FROM users u
               JOIN links l ON l.caregiver_id = u.telegram_id
               WHERE l.elder_id = ?""",
            (elder_id,),
        ).fetchall()


def get_elders_for_caregiver(caregiver_id: int):
    with get_conn() as conn:
        return conn.execute(
            """SELECT u.* FROM users u
               JOIN links l ON l.elder_id = u.telegram_id
               WHERE l.caregiver_id = ?""",
            (caregiver_id,),
        ).fetchall()


# -------------------------------------------------------- medications ----

def add_medication(elder_id: int, name: str, dose: str, times: str, days: str = "daily") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO medications (elder_id, name, dose, times, days) VALUES (?, ?, ?, ?, ?)",
            (elder_id, name, dose, times, days),
        )
        return cur.lastrowid


def list_medications(elder_id: int, active_only: bool = True):
    with get_conn() as conn:
        if active_only:
            return conn.execute(
                "SELECT * FROM medications WHERE elder_id = ? AND active = 1 ORDER BY name",
                (elder_id,),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM medications WHERE elder_id = ? ORDER BY name", (elder_id,)
        ).fetchall()


def get_medication(med_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM medications WHERE id = ?", (med_id,)).fetchone()


def deactivate_medication(med_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE medications SET active = 0 WHERE id = ?", (med_id,))


def all_active_medications():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM medications WHERE active = 1").fetchall()


# ----------------------------------------------------------------- logs ----

def log_exists_for_slot(medication_id: int, scheduled_for: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM logs WHERE medication_id = ? AND scheduled_for = ?",
            (medication_id, scheduled_for),
        ).fetchone()
        return row is not None


def create_log(medication_id: int, scheduled_for: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO logs (medication_id, scheduled_for) VALUES (?, ?)",
            (medication_id, scheduled_for),
        )
        return cur.lastrowid


def get_log(log_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM logs WHERE id = ?", (log_id,)).fetchone()


def update_log_status(log_id: int, status: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE logs SET status = ?, responded_at = ? WHERE id = ?",
            (status, _now_utc_iso(), log_id),
        )


def mark_nudged(log_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE logs SET nudged = 1 WHERE id = ?", (log_id,))


def mark_missed_and_escalated(log_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE logs SET status = 'missed', escalated = 1 WHERE id = ?", (log_id,)
        )


def pending_logs_older_than(minutes: int, not_nudged_only: bool = False):
    """Pending logs whose created_at (UTC) is more than `minutes` old."""
    cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    with get_conn() as conn:
        if not_nudged_only:
            return conn.execute(
                "SELECT * FROM logs WHERE status = 'pending' AND created_at <= ? AND nudged = 0",
                (cutoff,),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM logs WHERE status = 'pending' AND created_at <= ?",
            (cutoff,),
        ).fetchall()


def weekly_summary(elder_id: int):
    """Adherence counts for the last 7 days, per medication."""
    since = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)).isoformat(timespec="seconds")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT m.name AS med_name,
                      SUM(CASE WHEN l.status = 'taken' THEN 1 ELSE 0 END) AS taken,
                      SUM(CASE WHEN l.status = 'skipped' THEN 1 ELSE 0 END) AS skipped,
                      SUM(CASE WHEN l.status = 'missed' THEN 1 ELSE 0 END) AS missed,
                      SUM(CASE WHEN l.status = 'pending' THEN 1 ELSE 0 END) AS pending,
                      COUNT(*) AS total
               FROM logs l
               JOIN medications m ON m.id = l.medication_id
               WHERE m.elder_id = ? AND l.created_at >= ?
               GROUP BY m.id
               ORDER BY m.name""",
            (elder_id, since),
        ).fetchall()
        return rows
