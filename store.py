"""amygdala.store — 感情・関係性の永続化。

A版(mnemosyne)の DB とは別ファイル(amygdala.db)に持ち、A版の memory_id で
紐付ける。A版スキーマを汚さないための分離。

背景ワーカ(別スレッド)からも書くため、接続は check_same_thread=False とし、
書き込みはロックで直列化する(SQLite の単一ライタ制約に合わせる)。

テーブル:
  emotion(memory_id, joy, anger, sorrow, pleasure, neutral, partner_id, ts)
  relation(partner_id, affinity, trust, milestones, updated_ts)
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from amygdala.emotion import Emotion


_SCHEMA = """
CREATE TABLE IF NOT EXISTS emotion (
    memory_id  TEXT PRIMARY KEY,
    joy        REAL NOT NULL DEFAULT 0.0,
    anger      REAL NOT NULL DEFAULT 0.0,
    sorrow     REAL NOT NULL DEFAULT 0.0,
    pleasure   REAL NOT NULL DEFAULT 0.0,
    neutral    REAL NOT NULL DEFAULT 1.0,
    partner_id TEXT,
    ts         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_emotion_partner ON emotion(partner_id);

CREATE TABLE IF NOT EXISTS relation (
    partner_id  TEXT PRIMARY KEY,
    affinity    REAL NOT NULL DEFAULT 0.0,
    trust       REAL NOT NULL DEFAULT 0.0,
    milestones  TEXT NOT NULL DEFAULT '[]',
    updated_ts  REAL NOT NULL
);
"""


class EmotionStore:
    """memory_id → Emotion の永続化。"""

    def __init__(self, db_path: str = "amygdala.db"):
        # 背景ワーカから書くため check_same_thread=False。
        # 書き込みは self.lock で直列化する。
        self.con = sqlite3.connect(db_path, check_same_thread=False)
        self.lock = threading.Lock()
        self.con.executescript(_SCHEMA)
        self.con.execute("PRAGMA journal_mode = WAL;")
        self.con.execute("PRAGMA synchronous = NORMAL;")
        self.con.commit()

    def put(self, memory_id: str, emo: Emotion,
            partner_id: str | None = None, ts: float | None = None) -> None:
        with self.lock:
            self.con.execute(
                """INSERT INTO emotion
                   (memory_id, joy, anger, sorrow, pleasure, neutral, partner_id, ts)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(memory_id) DO UPDATE SET
                     joy=excluded.joy, anger=excluded.anger, sorrow=excluded.sorrow,
                     pleasure=excluded.pleasure, neutral=excluded.neutral,
                     partner_id=excluded.partner_id, ts=excluded.ts""",
                (memory_id, emo.joy, emo.anger, emo.sorrow, emo.pleasure,
                 emo.neutral, partner_id, ts or time.time()),
            )
            self.con.commit()

    def get(self, memory_id: str) -> Emotion:
        """未登録(=背景推定がまだ)の memory_id は neutral 既定を返す。"""
        row = self.con.execute(
            "SELECT joy, anger, sorrow, pleasure, neutral FROM emotion "
            "WHERE memory_id = ?", (memory_id,),
        ).fetchone()
        if row is None:
            return Emotion.neutral_default()
        return Emotion.from_list(list(row))

    def get_many(self, memory_ids: list[str]) -> dict[str, Emotion]:
        """再ランクで N 件まとめて引くため。未登録は neutral 既定で埋める。"""
        if not memory_ids:
            return {}
        ph = ",".join("?" * len(memory_ids))
        rows = self.con.execute(
            f"SELECT memory_id, joy, anger, sorrow, pleasure, neutral "
            f"FROM emotion WHERE memory_id IN ({ph})", memory_ids,
        ).fetchall()
        found = {r[0]: Emotion.from_list(list(r[1:])) for r in rows}
        return {mid: found.get(mid, Emotion.neutral_default())
                for mid in memory_ids}

    def close(self) -> None:
        self.con.close()
