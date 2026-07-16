"""amygdala の一連の流れを通しで見るデモ(mnemosyne 不要・LLM 不要)。

InMemoryCore + ルールベース分類器で、記憶 → 気分・関係性の更新 →
注入ブロック生成 → 想起、という会話ループの型を示す。

実行:
    python examples/chat_loop.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amygdala import InMemoryCore, MemoryRouter  # noqa: E402
from examples.rule_classifier import rule_classifier  # noqa: E402


def main() -> None:
    router = MemoryRouter(InMemoryCore(), db_path=":memory:",
                          classifier=rule_classifier)
    try:
        # --- 会話ターン: 体験を記録する ---
        events = [
            ("一緒に 大会で 優勝 して 嬉しかった", "user_42"),
            ("その後 打ち上げ が 楽しかった", "user_42"),
            ("翌日 些細な ことで 少し 喧嘩 して 悲しかった", "user_42"),
        ]
        for text, partner in events:
            router.remember(text, partner_id=partner)
            router.worker.drain_sync()  # デモ用に同期処理(本番は背景処理)
            router.tick_mood()          # 会話ターンごとに減衰を 1 tick

        # --- システムプロンプトへ注入するブロック ---
        print("=== state_block (hersona の injection block と並置する) ===")
        print(router.state_block(partner_id="user_42", lang="ja"))

        # --- 表現レイヤー(Live2D 等)へ渡す構造化データ ---
        print("\n=== export_state ===")
        print(router.export_state(partner_id="user_42"))

        # --- 感情・関係性つきの想起 ---
        print("\n=== recall('優勝 どうだった') ===")
        for hit in router.recall("優勝 どうだった",
                                 ctx={"partner_id": "user_42"}, k=3):
            print(f"  score={hit.score:.3f} "
                  f"dominant={hit.emotion.dominant()} "
                  f"text={hit.candidate.text!r}")

        print("\n=== worker stats ===")
        print(router.stats())
    finally:
        router.close()


if __name__ == "__main__":
    main()
