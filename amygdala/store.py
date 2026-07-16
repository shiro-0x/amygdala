"""amygdala.store — 感情・関係性の永続化。

mnemosyne の DB とは別ファイル(amygdala.db)に持ち、mnemosyne の memory_id で
紐付ける。mnemosyne スキーマを汚さないための分離。

背景ワーカ(別スレッド)からも書くため、接続は check_same_thread=False とし、
書き込みはロックで直列化する(SQLite の単一ライタ制約に合わせる)。
このロックは RelationStore と共有し、感情+関係性の複合更新を単一
トランザクションで行う(FR-2.6 冪等性 / FR-4.5 原子性)。

テーブル:
  emotion(memory_id, joy, anger, sorrow, pleasure, neutral, partner_id, ts)
  relation(partner_id, affinity, trust, milestones, updated_ts)
  processed_jobs(job_id, ts)  -- 感情ジョブの冪等性マーカ

制約: 同一 DB ファイルへの書き込みは単一プロセス内での直列化のみ保証する
(複数プロセスからの同時書き込みは対象外。REQUIREMENTS.md FR-4.5)。
"""
from __future__ import annotations

import sqlite3
import threading
import time

from amygdala.emotion import AXES, Emotion

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

CREATE TABLE IF NOT EXISTS processed_jobs (
    job_id TEXT PRIMARY KEY,
    ts     REAL NOT NULL
);
"""


class EmotionStore:
    """memory_id → Emotion の永続化と、感情ジョブの冪等適用。"""

    def __init__(self, db_path: str = "amygdala.db"):
        # 背景ワーカから書くため check_same_thread=False。
        # 書き込みは self.lock で直列化する。
        self.con = sqlite3.connect(db_path, check_same_thread=False)
        self.lock = threading.Lock()
        self.con.executescript(_SCHEMA)
        self.con.execute("PRAGMA journal_mode = WAL;")
        self.con.execute("PRAGMA synchronous = NORMAL;")
        self.con.commit()

    # --- 書き込み ---

    def put(self, memory_id: str, emo: Emotion,
            partner_id: str | None = None, ts: float | None = None) -> None:
        with self.lock:
            self._put_in_txn(memory_id, emo, partner_id, ts)
            self.con.commit()

    def _put_in_txn(self, memory_id: str, emo: Emotion,
                    partner_id: str | None, ts: float | None) -> None:
        """ロック取得済み・トランザクション内から呼ぶ(commit しない)。"""
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

    def apply_job(self, job_id: str, memory_id: str, emo: Emotion,
                  partner_id: str | None, relation_store=None,
                  relation_weight: float = 0.05) -> bool:
        """感情ジョブを冪等に適用する(FR-2.6)。

        processed_jobs へのマーカ挿入・感情の upsert・関係性更新を
        単一ロック内の単一トランザクションで行う。同じ job_id が既に
        処理済みなら何もせず False を返す(二重加算しない)。
        """
        with self.lock:
            cur = self.con.execute(
                "INSERT OR IGNORE INTO processed_jobs (job_id, ts) VALUES (?,?)",
                (job_id, time.time()),
            )
            if cur.rowcount == 0:  # 既処理 → スキップ
                self.con.rollback()
                return False
            try:
                self._put_in_txn(memory_id, emo, partner_id, None)
                if partner_id and relation_store is not None:
                    relation_store.apply_emotion_in_txn(
                        partner_id, emo, weight=relation_weight)
                self.con.commit()
            except Exception:
                self.con.rollback()
                raise
            return True

    # --- 読み出し ---

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

    def get_partner_map(self, memory_ids: list[str]) -> dict[str, str | None]:
        """memory_id → partner_id。候補への partner 復元に使う(FR-2.5)。

        mnemosyne は partner_id を知らないため、再ランクの相手一致項は
        必ずこのマップから復元する。未登録の memory_id は含めない。
        """
        if not memory_ids:
            return {}
        ph = ",".join("?" * len(memory_ids))
        rows = self.con.execute(
            f"SELECT memory_id, partner_id FROM emotion "
            f"WHERE memory_id IN ({ph})", memory_ids,
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    # --- データライフサイクル(NFR-12) ---

    def delete_memory(self, memory_id: str) -> int:
        """memory_id の感情レコードを削除する。削除件数を返す。"""
        with self.lock:
            cur = self.con.execute(
                "DELETE FROM emotion WHERE memory_id = ?", (memory_id,))
            self.con.commit()
            return cur.rowcount

    def delete_partner(self, partner_id: str) -> int:
        """partner に紐づく感情レコードを一括削除する。削除件数を返す。

        注意: 過去にこの partner の感情が関係性へ与えた累積影響は
        巻き戻さない(方針は REQUIREMENTS.md §10-7 参照)。関係性自体の
        削除は RelationStore.delete を使う。
        """
        with self.lock:
            cur = self.con.execute(
                "DELETE FROM emotion WHERE partner_id = ?", (partner_id,))
            self.con.commit()
            return cur.rowcount

    def export_partner(self, partner_id: str) -> list[dict]:
        """partner に紐づく感情レコードを dict のリストで返す。"""
        rows = self.con.execute(
            "SELECT memory_id, joy, anger, sorrow, pleasure, neutral, ts "
            "FROM emotion WHERE partner_id = ? ORDER BY memory_id",
            (partner_id,),
        ).fetchall()
        out = []
        for r in rows:
            rec = {"memory_id": r[0], "ts": r[6]}
            rec.update(dict(zip(AXES, r[1:6])))
            out.append(rec)
        return out

    def cleanup_orphans(self, live_memory_ids: set[str]) -> int:
        """mnemosyne 側に存在しない memory_id の感情レコードを削除する。

        呼び出し側が「生存している memory_id の全集合」を渡す。
        削除件数を返す。
        """
        rows = self.con.execute("SELECT memory_id FROM emotion").fetchall()
        orphans = [r[0] for r in rows if r[0] not in live_memory_ids]
        if not orphans:
            return 0
        with self.lock:
            ph = ",".join("?" * len(orphans))
            cur = self.con.execute(
                f"DELETE FROM emotion WHERE memory_id IN ({ph})", orphans)
            self.con.commit()
            return cur.rowcount

    def close(self) -> None:
        self.con.close()
