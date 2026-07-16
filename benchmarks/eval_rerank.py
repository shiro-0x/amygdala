"""FR-3.7: 二段ランクの採用根拠を残すベースライン評価。

感情なしベースライン(上流スコアのみ)と既定重みの二段ランクを、決定論的な
合成コーパスで比較する。記録する指標:

- Recall@k: 正解集合のうち上位 k に入った割合
- rank overlap: ベースラインと再ランクの上位 k の重なり(順位の入れ替わり量)
- latency: recall 1 回あたりの平均時間(InMemoryCore 経由の配線コスト)

正解の定義: クエリは「トピック × 相手」を狙う。同じトピックかつ同じ相手の
記憶を正解とする(partner 項と感情項が効けばベースラインより上がる設計)。

実行:
    python benchmarks/eval_rerank.py            # 結果を表示
    python benchmarks/eval_rerank.py --save     # benchmarks/results.json へ保存

乱数は使わない(テンプレート展開のみ)。同じコードは常に同じ結果を返す。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amygdala import (Emotion, InMemoryCore, MemoryRouter,  # noqa: E402
                      RerankWeights)

# k は正解集合サイズ(=2)に合わせる。k=6 では両者とも 1.0 に飽和して
# 差が見えないことを確認済み(2026-07-16)。
K = 2
TOPICS = {
    "勝利": "大会で 勝利 して 一緒に 喜んだ",
    "喧嘩": "些細な ことで 喧嘩 して 気まずく なった",
    "旅行": "旅行 で 海 を 見に 行った",
    "仕事": "仕事 の 締め切り に 追われた",
}
PARTNERS = ["alice", "bob", "carol"]
NOISE = [
    "天気 の 話 を した",
    "昼食 に 蕎麦 を 食べた",
    "本 を 読んで 過ごした",
]

# 決定論的なルール分類器: トピック語で感情を割り当てる
_RULES = {
    "勝利": Emotion(joy=0.9, pleasure=0.6, neutral=0.0),
    "喧嘩": Emotion(anger=0.8, sorrow=0.4, neutral=0.0),
    "旅行": Emotion(pleasure=0.7, joy=0.4, neutral=0.0),
    "仕事": Emotion(sorrow=0.3, neutral=0.4),
}


def rule_classifier(text: str) -> Emotion:
    for key, emo in _RULES.items():
        if key in text:
            return emo
    return Emotion.neutral_default()


def build_router(tmp_dir: Path) -> tuple[MemoryRouter, dict]:
    """コーパスを構築し、(router, クエリ→正解集合) を返す。

    重み比較は同一コーパス・同一 memory_id 上で行う(router.weights を
    差し替える)。別コーパスだと ID が変わり rank overlap が無意味になる。
    """
    router = MemoryRouter(
        InMemoryCore(), db_path=str(tmp_dir / "eval.db"),
        classifier=rule_classifier,
    )
    truth: dict[tuple[str, str], set[str]] = {}
    for topic, text in TOPICS.items():
        for partner in PARTNERS:
            # 同じトピック × 相手で 2 件ずつ(正解集合サイズ 2)
            ids = {router.remember(f"{text} {i}", partner_id=partner)
                   for i in range(2)}
            truth[(topic, partner)] = ids
    for i, text in enumerate(NOISE):
        for partner in PARTNERS:
            router.remember(f"{text} {i}", partner_id=partner)
    router.worker.drain_sync()
    return router, truth


def evaluate(router: MemoryRouter, truth: dict,
             weights: RerankWeights, label: str) -> dict:
    router.weights = weights
    recalls: list[float] = []
    latencies: list[float] = []
    rankings: dict[tuple[str, str], list[str]] = {}
    for (topic, partner), relevant in truth.items():
        query = TOPICS[topic]
        t0 = time.perf_counter()
        hits = router.recall(query, ctx={"partner_id": partner}, k=K)
        latencies.append((time.perf_counter() - t0) * 1000)
        top_ids = [h.candidate.memory_id for h in hits]
        rankings[(topic, partner)] = top_ids
        recalls.append(len(relevant & set(top_ids)) / len(relevant))
    return {
        "label": label,
        "weights": {"core": weights.core, "partner": weights.partner,
                    "emotion": weights.emotion,
                    "importance": weights.importance},
        f"recall@{K}": round(statistics.mean(recalls), 4),
        "latency_ms_mean": round(statistics.mean(latencies), 3),
        "_rankings": rankings,
    }


def rank_overlap(a: dict, b: dict) -> float:
    """クエリごとの上位 k の集合重なり率の平均(1.0 = 同一集合)。"""
    overlaps = []
    for key, ra in a["_rankings"].items():
        rb = b["_rankings"][key]
        union = set(ra) | set(rb)
        overlaps.append(len(set(ra) & set(rb)) / len(union) if union else 1.0)
    return round(statistics.mean(overlaps), 4)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", action="store_true",
                        help="benchmarks/results.json へ保存する")
    args = parser.parse_args()

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        router, truth = build_router(Path(td))
        try:
            baseline = evaluate(
                router, truth,
                RerankWeights(core=1.0, partner=0.0, emotion=0.0,
                              importance=0.0),
                "baseline (core only)")
            default = evaluate(router, truth, RerankWeights(),
                               "default weights")
        finally:
            router.close()

    overlap = rank_overlap(baseline, default)
    for r in (baseline, default):
        r.pop("_rankings")

    result = {
        "k": K,
        "corpus": {"topics": len(TOPICS), "partners": len(PARTNERS),
                   "memories": len(TOPICS) * len(PARTNERS) * 2
                               + len(NOISE) * len(PARTNERS)},
        "baseline": baseline,
        "default": default,
        "rank_overlap_topk": overlap,
        "note": ("正解 = 同一トピックかつ同一相手の記憶。partner/emotion 項が"
                 "効くと baseline より recall が上がる設計。latency は "
                 "InMemoryCore 経由の配線コスト(検索本体は含まない)。"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.save:
        out = Path(__file__).parent / "results.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"\nsaved: {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
