"""Memória local em SQLite: histórico de conversa + fatos sobre o usuário."""
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).parent / "faby.db"


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, role TEXT,
            content TEXT, emotion TEXT, ts REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS moods(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, emotion TEXT,
            intensity REAL, ts REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS facts(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, fact TEXT, ts REAL,
            UNIQUE(user_id, fact))""")


def add_message(user_id: str, role: str, content: str, emotion: str = "neutro"):
    with _conn() as c:
        c.execute("INSERT INTO messages(user_id, role, content, emotion, ts) VALUES(?,?,?,?,?)",
                  (user_id, role, content, emotion, time.time()))


def recent_messages(user_id: str, limit: int = 12) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def add_fact(user_id: str, fact: str):
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO facts(user_id, fact, ts) VALUES(?,?,?)",
                  (user_id, fact.strip(), time.time()))


def get_facts(user_id: str, limit: int = 30) -> list[str]:
    with _conn() as c:
        rows = c.execute("SELECT fact FROM facts WHERE user_id=? ORDER BY id DESC LIMIT ?",
                         (user_id, limit)).fetchall()
    return [r["fact"] for r in rows]


def forget_all(user_id: str):
    with _conn() as c:
        c.execute("DELETE FROM messages WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM facts WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM moods WHERE user_id=?", (user_id,))


def add_mood(user_id: str, emotion: str, intensity: float):
    with _conn() as c:
        c.execute("INSERT INTO moods(user_id, emotion, intensity, ts) VALUES(?,?,?,?)",
                  (user_id, emotion, float(intensity), time.time()))


def mood_summary(user_id: str, days: int = 7) -> str:
    """Resumo curto do humor recente, usado no prompt e no endpoint /mood."""
    since = time.time() - days * 86400
    with _conn() as c:
        rows = c.execute(
            "SELECT emotion, COUNT(*) AS n FROM moods WHERE user_id=? AND ts>? "
            "GROUP BY emotion ORDER BY n DESC", (user_id, since)).fetchall()
        last = c.execute("SELECT emotion, ts FROM moods WHERE user_id=? ORDER BY id DESC LIMIT 1",
                         (user_id,)).fetchone()
    if not rows or not last:
        return ""
    parts = ", ".join(f"{r['emotion']} {r['n']}x" for r in rows)
    mins = int((time.time() - last["ts"]) / 60)
    ago = f"há {mins} min" if mins < 90 else f"há {mins // 60} h"
    return f"Últimos {days} dias: {parts}. Último registro: {last['emotion']} ({ago})."
