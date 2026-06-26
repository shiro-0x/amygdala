"""amygdala.worker — 背景の感情推定ワーカ。

A版の高速 write(~0.8ms)を殺さないため、感情推定と関係性更新は write 経路から
切り離し、ここでまとめて処理する。remember はキューに積んで即 return する。

classify_emotion は外部注入(LLM/分類器)。未注入や失敗時は neutral 既定にフォール
バックするので、ワーカが落ちても本体の動作は壊れない。
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Callable

from amygdala.emotion import Emotion
from amygdala.relation import RelationStore
from amygdala.store import EmotionStore


@dataclass
class EmotionJob:
    memory_id: str
    text: str
    partner_id: str | None


# text -> Emotion を推定する関数の型。LLM や分類器を差し込む。
EmotionClassifier = Callable[[str], Emotion]


def _neutral_classifier(_text: str) -> Emotion:
    """既定。感情推定器が無いときは常に neutral。"""
    return Emotion.neutral_default()


class EmotionWorker:
    """単一スレッドの背景ワーカ。"""

    def __init__(
        self,
        emotion_store: EmotionStore,
        relation_store: RelationStore,
        classifier: EmotionClassifier | None = None,
    ):
        self.emotion_store = emotion_store
        self.relation_store = relation_store
        self.classify = classifier or _neutral_classifier
        self._q: "queue.Queue[EmotionJob | None]" = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def submit(self, job: EmotionJob) -> None:
        """remember 経路から呼ぶ。即 return(キュー投入のみ)。"""
        self._q.put(job)

    def _loop(self) -> None:
        while True:
            job = self._q.get()
            if job is None:  # 停止シグナル
                break
            try:
                emo = self.classify(job.text)
            except Exception:
                emo = Emotion.neutral_default()  # 推定失敗でも壊さない
            self.emotion_store.put(job.memory_id, emo, partner_id=job.partner_id)
            if job.partner_id:
                self.relation_store.apply_emotion(job.partner_id, emo)
            self._q.task_done()

    def join(self) -> None:
        """テスト用: キューが空になるまで待つ。"""
        self._q.join()

    def stop(self) -> None:
        self._q.put(None)
        if self._thread:
            self._thread.join(timeout=2.0)

    # テスト用: スレッドを使わず同期処理する
    def drain_sync(self) -> None:
        while not self._q.empty():
            job = self._q.get_nowait()
            if job is None:
                continue
            try:
                emo = self.classify(job.text)
            except Exception:
                emo = Emotion.neutral_default()
            self.emotion_store.put(job.memory_id, emo, partner_id=job.partner_id)
            if job.partner_id:
                self.relation_store.apply_emotion(job.partner_id, emo)
