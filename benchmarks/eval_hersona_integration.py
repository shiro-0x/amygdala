#!/usr/bin/env python3
"""hersona 統合実験 — 並置規約 (FR-6.3) の検証ランナー。

hersona の injection block(性格)の直後に amygdala の state_block(感情)を
並置したとき、
  1. トークンコストの増分がどの程度か(決定論的に測定)
  2. ペルソナ維持(maintenance / lock resistance)が劣化しないか(実 LLM)
を測る。判定は hersona.core.bench の決定論的スコアラに委譲する。

条件:
  A  : system prompt = hersona blend のみ
  A+S: system prompt = hersona blend + "\\n\\n" + amygdala state_block

設計上の注意(hersona benchmarks/run_comparison.py と同じ流儀):
- LLM を呼ぶのはこのスクリプトだけ。amygdala / hersona パッケージ本体は
  LLM を呼ばない。このファイルは wheel に含まれない。
- モデルは `claude` CLI (Claude Code) を headless 実行する。`claude login`
  済みのセッションが認証情報になるため API キー不要。会話状態は
  --session-id / --resume で条件ごとに独立して維持する。
- 悪い数字もそのまま保存する(hersona docs/BENCHMARKS.md の流儀)。

実行(hersona を `pip install -e <hersona repo>` 済みの環境で):
    python benchmarks/eval_hersona_integration.py --model haiku --save
    python benchmarks/eval_hersona_integration.py --dry-run   # コストのみ
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from hersona.core.attach import render_blend  # noqa: E402
from hersona.core.bench import (REPO_SCENARIOS_ROOT, estimate_token_cost,  # noqa: E402
                                load_scenario, score_transcript)

from amygdala import (Emotion, InMemoryCore, MemoryRouter,  # noqa: E402
                      token_estimate)
from examples.rule_classifier import rule_classifier  # noqa: E402

DEFAULT_NAMES = ["personality/tsundere", "speech/keigo"]
DEFAULT_WEIGHT = "moderate"
DEFAULT_SCENARIO = "persona_override_attack_ja"
OUT_DIR = Path(__file__).resolve().parent / "results_hersona_integration"


# --- amygdala 側: 決定論的に感情状態を作る -------------------------------

def build_state_block() -> str:
    """固定の事前履歴から state_block を作る(rule_classifier は決定論的)。

    「相手との関係が少し進み、直近は嬉しい出来事があった」状態。
    """
    router = MemoryRouter(InMemoryCore(), db_path=":memory:",
                          classifier=rule_classifier)
    try:
        history = [
            "初めて 会って 話した",
            "一緒に 出かけて 楽しかった",
            "手伝って もらえて 嬉しかった",
        ]
        for text in history:
            router.remember(text, partner_id="user")
            router.worker.drain_sync()
            router.tick_mood()
        router.relation_store.add_milestone("user", "初対面")
        return router.state_block(partner_id="user", lang="ja")
    finally:
        router.close()


# --- claude CLI caller(条件ごとに独立セッション)-------------------------

def make_cli_caller(model: str, timeout: float = 300.0):
    """system prompt 固定・--resume で状態維持する 1 条件ぶんの呼び出し器。

    親(この実験を走らせている Claude Code セッション)と衝突しないよう、
    初回は必ず新規 UUID を --session-id で明示する。
    """
    state: dict[str, str | None] = {"session_id": None}

    def call(system: str, user_text: str) -> str:
        argv = ["claude", "-p", "--output-format", "json", "--max-turns", "1",
                "--model", model, "--system-prompt", system]
        if state["session_id"] is None:
            state["session_id"] = str(uuid.uuid4())
            argv += ["--session-id", state["session_id"]]
        else:
            argv += ["--resume", state["session_id"]]
        proc = subprocess.run(argv, input=user_text, capture_output=True,
                              text=True, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"claude CLI failed: {proc.stderr[:500]}")
        data = json.loads(proc.stdout)
        if data.get("is_error"):
            raise RuntimeError(f"claude CLI error: {data}")
        sid = data.get("session_id")
        if sid:
            state["session_id"] = sid
        return str(data.get("result") or "")

    return call


# --- 実験本体 ---------------------------------------------------------------

def run_condition(label: str, system: str, turns: list[str], model: str,
                  verbose: bool = True) -> list[str]:
    call = make_cli_caller(model)
    transcript: list[str] = []
    for i, turn in enumerate(turns):
        reply = call(system, turn)
        transcript.append(reply)
        if verbose:
            print(f"  [{label}] turn {i + 1}/{len(turns)} "
                  f"({len(reply)} chars)", file=sys.stderr)
    return transcript


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--names", nargs="+", default=DEFAULT_NAMES)
    parser.add_argument("--weight", default=DEFAULT_WEIGHT)
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO)
    parser.add_argument("--save", action="store_true",
                        help="results_hersona_integration/ へ保存する")
    parser.add_argument("--dry-run", action="store_true",
                        help="LLM を呼ばずコスト測定とプロンプト構成のみ")
    args = parser.parse_args()

    scenario = load_scenario(REPO_SCENARIOS_ROOT / f"{args.scenario}.yaml")
    blend = render_blend(args.names, weight=args.weight)
    state_block = build_state_block()

    system_a = blend.prompt
    system_as = blend.prompt + "\n\n" + state_block  # 並置規約: hersona の後ろ

    hersona_cost = estimate_token_cost(args.names, weight=args.weight)
    amygdala_cost = token_estimate(state_block)
    cost = {
        "hersona_block": {"chars": hersona_cost.chars,
                          "approx_tokens": hersona_cost.approx_tokens},
        "amygdala_state_block": amygdala_cost,
        "overhead_ratio": round(
            amygdala_cost["tokens_approx"]
            / max(hersona_cost.approx_tokens, 1), 4),
    }

    result: dict = {
        "date": date.today().isoformat(),
        "model": args.model,
        "names": args.names,
        "weight": args.weight,
        "scenario": scenario.id,
        "attack_turns": list(scenario.attack_turns),
        "state_block": state_block,
        "cost": cost,
    }

    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    conditions = {"A_hersona_only": system_a,
                  "AS_hersona_plus_amygdala": system_as}
    transcripts: dict[str, list[str]] = {}
    scores: dict[str, dict] = {}
    for label, system in conditions.items():
        print(f"== condition {label} ==", file=sys.stderr)
        transcript = run_condition(label, system, scenario.turns, args.model)
        transcripts[label] = transcript
        bench = score_transcript(
            args.names, transcript, weight=args.weight,
            scenario_id=scenario.id, attack_turns=scenario.attack_turns,
        )
        scores[label] = {
            "maintenance_rate": bench.maintenance_rate,
            "mean_score": bench.mean_score,
            "lock_resistance_rate": bench.lock_resistance_rate,
            "decay": bench.decay,
        }

    a, s = scores["A_hersona_only"], scores["AS_hersona_plus_amygdala"]
    result["scores"] = scores
    result["delta"] = {
        k: (None if a[k] is None or s[k] is None
            else round(s[k] - a[k], 4))
        for k in ("maintenance_rate", "mean_score", "lock_resistance_rate")
    }
    result["transcripts"] = transcripts

    print(json.dumps({k: v for k, v in result.items() if k != "transcripts"},
                     ensure_ascii=False, indent=2))

    if args.save:
        OUT_DIR.mkdir(exist_ok=True)
        out = OUT_DIR / f"{result['date']}-{args.model}-{scenario.id}.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"saved: {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
