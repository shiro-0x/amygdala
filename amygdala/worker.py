"""amygdala.worker — 背景の感情推定ワーカ。

mnemosyne の高速 write を殺さないため、感情推定と関係性更新は write 経路から
切り離し、ここでまとめて処理する。remember はキューに積んで即 return する。

classify_emotion は外部注入(LLM/分類器)。未注入や失敗時は neutral(無)既定に
フォールバックするので、ワーカが落ちても本体の動作は壊れない。

耐障害性(NFR-5 / NFR-10):
- ジョブ全体(分類・DB 書き込み・関係更新)の例外を捕捉し、ワーカスレッドは
  無言で死なない(logging.exception + stats に記録)。
- task_done() は finally で保証する。
- キューは有界(既定 1024)。満杯時は新規ジョブを破棄して警告を出す
  (drop-new 方針。write 経路をブロックしないことを優先)。
- stop() は停止シグナルをキュー末尾に積むため、先行ジョブは処理されてから
  停止する(drain)。タイムアウト後もスレッドが残る場合は警告を出す。
- 永続キューではないため、プロセス異常終了時に未処理ジョブは失われる
  (best-effort。README に明記)。

冪等性(FR-2.6): 適用は EmotionStore.apply_job 経由で行い、同じ job_id の
二重処理では関係性・感情を二重更新しない。job_id は既定で memory_id
(1 記憶 = 1 感情ジョブ)。

可観測性(NFR-11): stats() でキュー深さ・成功/失敗/フォールバック/破棄/
重複スキップ数・最終処理時刻を返す。
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from amygdala.emotion import Emotion
from amygdala.relation import RelationStore
from amygdala.store import EmotionStore

log = logging.getLogger(__name__)

DEFAULT_QUEUE_MAXSIZE = 1024


@dataclass
class EmotionJob:
    memory_id: str
    text: str
    partner_id: str | None
    # 冪等性キー。既定は memory_id(1 記憶 = 1 感情ジョブ)。
    job_id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.job_id:
            self.job_id = self.memory_id


# text -> Emotion を推定する関数の型。LLM や分類器を差し込む。
EmotionClassifier = Callable[[str], Emotion]

# text -> milestone ラベル列 を推定する関数の型(v1.2, 注入式)。
# classifier と同型の外部注入。失敗時は検出なしにフォールバックする。
MilestoneDetector = Callable[[str], "list[str]"]


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
        queue_maxsize: int = DEFAULT_QUEUE_MAXSIZE,
        relation_weight: float = 0.05,
        mood_alpha: float | None = None,
        interaction: "Callable[[Emotion], Emotion] | None" = None,
        milestone_detector: MilestoneDetector | None = None,
    ):
        self.emotion_store = emotion_store
        self.relation_store = relation_store
        self.classify = classifier or _neutral_classifier
        self.relation_weight = relation_weight
        self.mood_alpha = mood_alpha  # None なら気分は更新しない
        self.interaction = interaction  # None なら感情間相互作用なし
        self.detect_milestones = milestone_detector  # None なら検出なし
        self._q: "queue.Queue[EmotionJob | None]" = queue.Queue(
            maxsize=queue_maxsize)
        self._thread: threading.Thread | None = None
        self._stats_lock = threading.Lock()
        self._stats = {
            "processed": 0,          # 正常に適用したジョブ数
            "failed": 0,             # 適用中に例外になったジョブ数
            "fallbacks": 0,          # 分類失敗で neutral に落ちた数
            "dropped": 0,            # キュー満杯で破棄した数
            "skipped_duplicates": 0, # 冪等スキップした数
            "last_processed_ts": None,
        }

    # --- ライフサイクル ---

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """停止する。キュー末尾に停止シグナルを積むため先行ジョブは drain される。"""
        try:
            self._q.put_nowait(None)
        except queue.Full:
            # 満杯なら少し待って積む(それでも無理なら諦めてスレッドを待つ)
            try:
                self._q.put(None, timeout=timeout)
            except queue.Full:
                log.warning("worker queue full; stop signal not enqueued")
        if self._thread:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                log.warning("worker thread did not stop within %.1fs", timeout)

    # --- 投入 ---

    def submit(self, job: EmotionJob) -> bool:
        """remember 経路から呼ぶ。即 return(キュー投入のみ)。

        キュー満杯時はジョブを破棄して False を返す(write をブロックしない)。
        破棄された記憶は neutral 既定のまま動作する。
        """
        try:
            self._q.put_nowait(job)
            return True
        except queue.Full:
            with self._stats_lock:
                self._stats["dropped"] += 1
            log.warning("worker queue full; dropping emotion job for %s",
                        job.memory_id)
            return False

    # --- 処理 ---

    def _process(self, job: EmotionJob) -> None:
        """1 ジョブを分類→冪等適用する。例外は呼び出し側で捕捉する。"""
        try:
            emo = self.classify(job.text)
        except Exception:
            log.exception("emotion classifier failed for %s; falling back to "
                          "neutral", job.memory_id)
            emo = Emotion.neutral_default()
            with self._stats_lock:
                self._stats["fallbacks"] += 1
        # 感情間相互作用(オプトイン)。失敗しても生値のまま続行。
        if self.interaction is not None:
            try:
                emo = self.interaction(emo)
            except Exception:
                log.exception("interaction failed for %s; using raw emotion",
                              job.memory_id)
        # milestone 自動検出(注入式)。失敗・partner なしなら検出なし。
        milestones: list[str] | None = None
        if self.detect_milestones is not None and job.partner_id:
            try:
                found = self.detect_milestones(job.text)
                milestones = list(found) if found else None
            except Exception:
                log.exception("milestone detector failed for %s; skipping",
                              job.memory_id)
        applied = self.emotion_store.apply_job(
            job.job_id, job.memory_id, emo, job.partner_id,
            relation_store=self.relation_store,
            relation_weight=self.relation_weight,
            mood_alpha=self.mood_alpha,
            milestones=milestones,
        )
        with self._stats_lock:
            if applied:
                self._stats["processed"] += 1
            else:
                self._stats["skipped_duplicates"] += 1
            self._stats["last_processed_ts"] = time.time()

    def _loop(self) -> None:
        while True:
            job = self._q.get()
            try:
                if job is None:  # 停止シグナル
                    return
                self._process(job)
            except Exception:
                # DB 例外等でもワーカは死なない(該当記憶は neutral 既定のまま)
                log.exception("emotion job failed for %s",
                              getattr(job, "memory_id", "?"))
                with self._stats_lock:
                    self._stats["failed"] += 1
            finally:
                self._q.task_done()

    # --- 可観測性 ---

    def stats(self) -> dict:
        """キュー深さと処理カウンタのスナップショットを返す(NFR-11)。"""
        with self._stats_lock:
            snap = dict(self._stats)
        snap["queue_depth"] = self._q.qsize()
        return snap

    def join(self) -> None:
        """テスト用: キューが空になるまで待つ。"""
        self._q.join()

    # テスト用: スレッドを使わず同期処理する(本処理と同じ経路を通す)
    def drain_sync(self) -> None:
        while True:
            try:
                job = self._q.get_nowait()
            except queue.Empty:
                return
            try:
                if job is None:
                    continue
                self._process(job)
            except Exception:
                log.exception("emotion job failed for %s",
                              getattr(job, "memory_id", "?"))
                with self._stats_lock:
                    self._stats["failed"] += 1
            finally:
                self._q.task_done()
