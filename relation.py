"""amygdala.relation — 関係性進行。

体験の感情ベクトルから affinity(好感度)/trust(信頼)/milestones を更新する。
喜・楽で affinity↑、怒・哀で↓、無は影響なし。喜びは trust にも寄与。

関係状態は recall 時に常時注入される(STM境界除外の対象外、常に最新値を一度返す)。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from amygdala.emotion import Emotion


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


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

    def to_context(self) -> str:
        """recall 時に注入する短い関係状態サマリ。"""
        parts = [f"partner={self.partner_id}",
                 f"affinity={self.affinity:+.2f}",
                 f"trust={self.trust:+.2f}"]
        if self.milestones:
            parts.append("milestones=" + ",".join(self.milestones))
        return "RELATION| " + " ".join(parts)


class RelationStore:
    """RelationState の永続化。EmotionStore と同じ DB 接続を共有する。"""

    def __init__(self, con, lock=None):
        self.con = con  # sqlite3.Connection（store.py で生成済み）
        # EmotionStore と同じロックを共有して書き込みを直列化する
        import threading
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
            self.con.commit()

    def apply_emotion(self, partner_id: str, emo: Emotion,
                      weight: float = 0.05) -> RelationState:
        """get → apply → save を一括で行う(背景ワーカから呼ぶ)。"""
        state = self.get(partner_id)
        state.apply_emotion(emo, weight=weight)
        self.save(state)
        return state
