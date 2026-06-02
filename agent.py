# -*- coding: utf-8 -*-
"""
Investigation Agent — main entry point.

Usage:
    python agent.py

Environment variables required:
    ANTHROPIC_API_KEY   — Anthropic API key
    GITHUB_TOKEN        — GitHub personal access token (read:repo scope)
"""

import os
import sys

import anthropic

from prompts import SYSTEM_PROMPT, INITIAL_PROMPT
from tools import TOOLS, execute_tools

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 16000
MAX_TURNS = 50  # safety limit


def run_agent() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: 環境変数 ANTHROPIC_API_KEY が設定されていません。", file=sys.stderr)
        sys.exit(1)

    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        print("WARNING: GITHUB_TOKEN が未設定です。GitHub API のレート制限が厳しくなります。")

    client = anthropic.Anthropic(api_key=api_key)

    print("=" * 60)
    print("Investigation Agent 起動")
    print(f"モデル : {MODEL}")
    print(f"GitHub : {'認証あり' if github_token else '未認証（レート制限注意）'}")
    print("=" * 60)

    messages: list[dict] = [
        {"role": "user", "content": INITIAL_PROMPT}
    ]

    turn = 0
    while turn < MAX_TURNS:
        turn += 1
        print(f"\n[Turn {turn}] Claude に送信中...", flush=True)

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Show stop reason
        print(f"  stop_reason: {response.stop_reason}")

        # Collect text output for logging
        for block in response.content:
            if hasattr(block, "text") and block.text:
                preview = block.text[:200].replace("\n", " ")
                print(f"  [TEXT] {preview}{'...' if len(block.text) > 200 else ''}")
            elif block.type == "tool_use":
                args_preview = str(block.input)[:120]
                print(f"  [TOOL] {block.name}({args_preview})")

        # Finished
        if response.stop_reason == "end_turn":
            print("\n調査完了。")
            break

        # Execute tools
        if response.stop_reason == "tool_use":
            tool_results = execute_tools(response.content)

            # Show tool result previews
            for r in tool_results:
                preview = r["content"][:200].replace("\n", " ")
                print(f"  [RESULT] {preview}{'...' if len(r['content']) > 200 else ''}")

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user",      "content": tool_results})
        elif response.stop_reason == "max_tokens":
            # Continue: append what we have and let Claude finish
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": [
                {"type": "text", "text": "続きを書いてください。write_report ツールでレポートを保存してください。"}
            ]})
        else:
            print(f"予期しない stop_reason: {response.stop_reason}")
            break
    else:
        print(f"\nWARNING: ターン上限 ({MAX_TURNS}) に達しました。")

    print("\n" + "=" * 60)
    print("Investigation Agent 終了")
    print("=" * 60)


if __name__ == "__main__":
    run_agent()
