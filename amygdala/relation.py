"""amygdala.relation — 関係性進行。

体験の感情ベクトルから affinity(好感度)/trust(信頼)/milestones を更新する。
喜・楽で affinity↑、怒・哀で↓、無は影響なし。喜びは trust にも寄与。

関係状態は recall 時に常時注入される(STM境界除外の対象外、常に最新値を一度返す)。

並行性(FR-4.5): get → apply → save は EmotionStore と共有するロックの中で
単一トランザクションとして実行し、複数スレッドからの lost update を防ぐ。
複数プロセスからの同時書き込みは対象外(単一プロセス専用)。
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field

from amygdala.emotion import Emotion


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# 関係性の時間減衰の既定率(1 tick あたり)。気分(mood.DEFAULT_DECAY_RATE=0.1)
# より一桁遅い: 感情=速い / 気分=遅い / 関係=最も遅い、の三速構成(FR-4.4)。
DEFAULT_RELATION_DECAY_RATE = 0.01


@dataclass
class RelationState:
    partner_id: str
    affinity: float = 0.0   # 好感度 -1.0〜1.0
    trust: float = 0.0      # 信頼   -1.0〜1.0
    milestones: list[str] = field(default_factory=list)

    def apply_emotion(self, emo: Emotion, weight: float = 0.05) -> None:
        """体験の感情から関係性を更新する。

        喜・楽 → affinity 上昇、怒・哀 → 低下。無は影響なし。
        喜び(joy)は trust にも寄与する。
        """
        self.affinity = _clamp(
            self.affinity
            + weight * (emo.joy + emo.pleasure)
            - weight * (emo.anger + emo.sorrow)
        )
        self.trust = _clamp(self.trust + weight * emo.joy)

    def add_milestone(self, label: str) -> None:
        if label not in self.milestones:
            self.milestones.append(label)

    def decay(self, ticks: int = 1,
              rate: float = DEFAULT_RELATION_DECAY_RATE) -> None:
        """交流が無い期間の経過で affinity / trust を 0 へ減衰させる(FR-4.4)。

        1 tick の単位(日・セッション等)は呼び出し側が決める。決定論的。
        milestones(節目の事実)は減衰しない。
        """
        if ticks < 0:
            raise ValueError(f"ticks must be >= 0, got {ticks}")
        if not 0.0 <= rate <= 1.0:
            raise ValueError(f"rate must be in [0, 1], got {rate}")
        factor = (1.0 - rate) ** ticks
        self.affinity *= factor
        self.trust *= factor

    def to_context(self) -> str:
        """recall 時に注入する短い関係状態サマリ。"""
        parts = [f"partner={self.partner_id}",
                 f"affinity={self.affinity:+.2f}",
                 f"trust={self.trust:+.2f}"]
        if self.milestones:
            parts.append("milestones=" + ",".join(self.milestones))
        return "RELATION| " + " ".join(parts)


class RelationStore:
    """RelationState の永続化。EmotionStore と同じ DB 接続・ロックを共有する。"""

    def __init__(self, con, lock=None):
        self.con = con  # sqlite3.Connection(store.py で生成済み)
        # EmotionStore と同じロックを共有して書き込みを直列化する
        self.lock = lock or threading.Lock()

    def get(self, partner_id: str) -> RelationState:
        row = self.con.execute(
            "SELECT affinity, trust, milestones FROM relation "
            "WHERE partner_id = ?", (partner_id,),
        ).fetchone()
        if row is None:
            return RelationState(partner_id=partner_id)
        return RelationState(
            partner_id=partner_id,
            affinity=row[0], trust=row[1],
            milestones=json.loads(row[2]),
        )

    def save(self, state: RelationState) -> None:
        with self.lock:
            self._save_in_txn(state)
            self.con.commit()

    def _save_in_txn(self, state: RelationState) -> None:
        """ロック取得済み・トランザクション内から呼ぶ(commit しない)。"""
        self.con.execute(
            """INSERT INTO relation
               (partner_id, affinity, trust, milestones, updated_ts)
               VALUES (?,?,?,?,?)
               ON CONFLICT(partner_id) DO UPDATE SET
                 affinity=excluded.affinity, trust=excluded.trust,
                 milestones=excluded.milestones, updated_ts=excluded.updated_ts""",
            (state.partner_id, state.affinity, state.trust,
             json.dumps(state.milestones, ensure_ascii=False), time.time()),
        )

    def apply_emotion_in_txn(self, partner_id: str, emo: Emotion,
                             weight: float = 0.05,
                             milestones: list[str] | None = None
                             ) -> RelationState:
        """ロック取得済み・トランザクション内での get → apply(+milestone)→ save。

        EmotionStore.apply_job(感情ジョブの冪等適用)から呼ばれる。
        commit は呼び出し側が行う。milestones を渡すと同一状態へ追記する
        (冪等ジョブの一部として原子的に)。
        """
        state = self.get(partner_id)
        state.apply_emotion(emo, weight=weight)
        for label in milestones or ():
            state.add_milestone(label)
        self._save_in_txn(state)
        return state

    def apply_emotion(self, partner_id: str, emo: Emotion,
                      weight: float = 0.05) -> RelationState:
        """get → apply → save を単一ロック・単一トランザクションで行う。"""
        with self.lock:
            try:
                state = self.apply_emotion_in_txn(partner_id, emo, weight=weight)
                self.con.commit()
            except Exception:
                self.con.rollback()
                raise
            return state

    def add_milestone(self, partner_id: str, label: str) -> RelationState:
        """milestone を原子的に追加する。"""
        with self.lock:
            try:
                state = self.get(partner_id)
                state.add_milestone(label)
                self._save_in_txn(state)
                self.con.commit()
            except Exception:
                self.con.rollback()
                raise
            return state

    def decay(self, partner_id: str, ticks: int = 1,
              rate: float = DEFAULT_RELATION_DECAY_RATE) -> RelationState:
        """get → decay → save を単一ロック・単一トランザクションで行う。"""
        with self.lock:
            try:
                state = self.get(partner_id)
                state.decay(ticks=ticks, rate=rate)
                self._save_in_txn(state)
                self.con.commit()
            except Exception:
                self.con.rollback()
                raise
            return state

    def delete(self, partner_id: str) -> int:
        """partner の関係性レコードを削除する(NFR-12)。削除件数を返す。"""
        with self.lock:
            cur = self.con.execute(
                "DELETE FROM relation WHERE partner_id = ?", (partner_id,))
            self.con.commit()
            return cur.rowcount
