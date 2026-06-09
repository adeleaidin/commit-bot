import sqlite3
import os
from datetime import date, datetime

DB_PATH = os.environ.get("DB_PATH", "commit_club.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                display_name TEXT NOT NULL,
                goal        TEXT NOT NULL,
                is_anon     INTEGER DEFAULT 0,
                xp          INTEGER DEFAULT 0,
                aura        INTEGER DEFAULT 0,
                streak      INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0,
                rank        TEXT DEFAULT 'E',
                joined_at   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS reports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                report_date TEXT NOT NULL,
                text        TEXT,
                has_photo   INTEGER DEFAULT 0,
                xp_earned   INTEGER DEFAULT 0,
                submitted_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, report_date)
            );

            CREATE TABLE IF NOT EXISTS callouts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                callout_date TEXT NOT NULL,
                code        TEXT NOT NULL,
                UNIQUE(user_id, callout_date)
            );
        """)


RANK_THRESHOLDS = [
    (0,    "E"),
    (100,  "D"),
    (300,  "C"),
    (700,  "B"),
    (1500, "A"),
    (3000, "S"),
]

XP_BASE        = 10   # text report
XP_PHOTO_BONUS = 5    # has photo
XP_EARLY_BONUS = 5    # before 12:00 local (UTC+6 for KG, simplified as UTC here)
XP_STREAK_7    = 50   # 7-day streak milestone
XP_CALLOUT     = 20   # attended callout


def calc_rank(xp: int) -> str:
    rank = "E"
    for threshold, r in RANK_THRESHOLDS:
        if xp >= threshold:
            rank = r
    return rank


def get_user(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def register_user(user_id: int, username: str, display_name: str, goal: str, is_anon: bool):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO users (user_id, username, display_name, goal, is_anon)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                display_name=excluded.display_name,
                goal=excluded.goal,
                is_anon=excluded.is_anon
        """, (user_id, username or "", display_name, goal, int(is_anon)))


def submit_report(user_id: int, text: str, has_photo: bool) -> dict:
    today = date.today().isoformat()
    now_hour = datetime.utcnow().hour  # UTC; adjust offset if needed

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM reports WHERE user_id=? AND report_date=?",
            (user_id, today)
        ).fetchone()
        if existing:
            return {"error": "already_reported"}

        user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not user:
            return {"error": "not_registered"}

        xp = XP_BASE
        reasons = [f"+{XP_BASE} XP за отчёт"]

        if has_photo:
            xp += XP_PHOTO_BONUS
            reasons.append(f"+{XP_PHOTO_BONUS} за фото")

        if now_hour < 12:
            xp += XP_EARLY_BONUS
            reasons.append(f"+{XP_EARLY_BONUS} ранний старт")

        # streak calculation
        yesterday = (date.today().toordinal() - 1)
        yesterday_str = date.fromordinal(yesterday).isoformat()
        had_yesterday = conn.execute(
            "SELECT id FROM reports WHERE user_id=? AND report_date=?",
            (user_id, yesterday_str)
        ).fetchone()

        new_streak = (user["streak"] + 1) if had_yesterday else 1
        streak_bonus = 0
        if new_streak == 7:
            streak_bonus = XP_STREAK_7
            xp += streak_bonus
            reasons.append(f"+{XP_STREAK_7} 🔥 7-дневный стрик!")

        new_xp = user["xp"] + xp
        new_aura = user["aura"] + xp
        new_rank = calc_rank(new_xp)
        rank_up = new_rank != user["rank"]
        best_streak = max(user["best_streak"], new_streak)

        conn.execute("""
            INSERT INTO reports (user_id, report_date, text, has_photo, xp_earned)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, today, text, int(has_photo), xp))

        conn.execute("""
            UPDATE users SET
                xp=?, aura=?, streak=?, best_streak=?, rank=?
            WHERE user_id=?
        """, (new_xp, new_aura, new_streak, best_streak, new_rank, user_id))

        return {
            "xp_earned": xp,
            "reasons": reasons,
            "total_xp": new_xp,
            "aura": new_aura,
            "streak": new_streak,
            "rank": new_rank,
            "rank_up": rank_up,
            "old_rank": user["rank"],
            "streak_bonus": streak_bonus,
            "display_name": user["display_name"],
            "goal": user["goal"],
            "is_anon": bool(user["is_anon"]),
        }


def mark_callout(user_id: int, code: str, expected_code: str) -> dict:
    if code.upper() != expected_code.upper():
        return {"error": "wrong_code"}
    today = date.today().isoformat()
    with get_conn() as conn:
        user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not user:
            return {"error": "not_registered"}
        try:
            conn.execute(
                "INSERT INTO callouts (user_id, callout_date, code) VALUES (?, ?, ?)",
                (user_id, today, code.upper())
            )
        except sqlite3.IntegrityError:
            return {"error": "already_marked"}
        new_xp = user["xp"] + XP_CALLOUT
        new_aura = user["aura"] + XP_CALLOUT
        new_rank = calc_rank(new_xp)
        conn.execute(
            "UPDATE users SET xp=?, aura=?, rank=? WHERE user_id=?",
            (new_xp, new_aura, new_rank, user_id)
        )
        return {"xp_earned": XP_CALLOUT, "total_xp": new_xp, "display_name": user["display_name"]}


def get_daily_leaderboard() -> list:
    today = date.today().isoformat()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT u.display_name, u.is_anon, u.rank, u.xp, u.streak, r.xp_earned
            FROM reports r
            JOIN users u ON u.user_id = r.user_id
            WHERE r.report_date = ?
            ORDER BY r.xp_earned DESC, u.xp DESC
            LIMIT 10
        """, (today,)).fetchall()
    return [dict(r) for r in rows]


def get_user_profile(user_id: int) -> dict | None:
    today = date.today().isoformat()
    with get_conn() as conn:
        user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not user:
            return None
        reported_today = conn.execute(
            "SELECT id FROM reports WHERE user_id=? AND report_date=?",
            (user_id, today)
        ).fetchone()
        total_reports = conn.execute(
            "SELECT COUNT(*) as cnt FROM reports WHERE user_id=?",
            (user_id,)
        ).fetchone()["cnt"]
        return {
            **dict(user),
            "reported_today": bool(reported_today),
            "total_reports": total_reports,
        }


def update_user_name(user_id: int, new_name: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET display_name=? WHERE user_id=?",
            (new_name, user_id)
        )


def update_user_goal(user_id: int, new_goal: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET goal=? WHERE user_id=?",
            (new_goal, user_id)
        )


def get_users_without_report() -> list:
    today = date.today().isoformat()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT u.user_id, u.display_name
            FROM users u
            WHERE u.user_id NOT IN (
                SELECT user_id FROM reports WHERE report_date=?
            )
        """, (today,)).fetchall()
    return [dict(r) for r in rows]
