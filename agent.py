# -*- coding: utf-8 -*-
"""
Investigation Agent — main entry point.

Usage:
    python agent.py

Environment variables required:
    DEEPSEEK_API_KEY    — Deepseek API key
    GITHUB_TOKEN        — GitHub personal access token (read:repo scope)
"""

import json
import os
import sys

from openai import OpenAI

from prompts import SYSTEM_PROMPT, INITIAL_PROMPT
from tools import TOOLS, execute_tools

MODEL = "deepseek-chat"
MAX_TOKENS = 16000
MAX_TURNS = 100  # safety limit (increased from 50)


def execute_tools_openai(tool_use_blocks: list) -> list:
    """Execute tool use blocks (OpenAI format) and return tool results."""
    results = []
    for block in tool_use_blocks:
        name  = block["name"]
        args  = block["input"]
        try:
            # Use the execute_tools function from tools module
            # Create a mock anthropic-like block
            class MockBlock:
                def __init__(self, name, input_dict, id_val):
                    self.type = "tool_use"
                    self.name = name
                    self.input = input_dict
                    self.id = id_val
            
            mock_block = MockBlock(name, args, block["id"])
            tool_result = execute_tools([mock_block])
            if tool_result:
                results.append(tool_result[0])
        except Exception as e:
            results.append({
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": f"ERROR ({name}): {e}"
            })
    return results


def parse_dsml_tool_calls(text: str) -> list[dict]:
    """Parse Deepseek DSML-style tool calls from response text."""
    import re

    def parse_simple_args(blob: str) -> dict:
        args = {}
        for arg_match in re.finditer(r"<(?P<name>[^>\s]+)>(?P<value>.*?)</(?P=name)>", blob, re.S):
            args[arg_match.group("name")] = arg_match.group("value").strip()
        return args

    def parse_parameters(block: str) -> dict:
        args = {}
        for arg_match in re.finditer(r"<[^>]*?parameter\s+name=\"(?P<name>[^\"]+)\"[^>]*>(?P<value>.*?)</[^>]*?parameter[^>]*>", block, re.S):
            args[arg_match.group("name")] = arg_match.group("value").strip()
        return args

    tool_calls = []
    idx = 0

    # React task invocation format
    for match in re.finditer(r"<react_task_invoke>(?P<body>.*?)</react_task_invoke>", text, re.S):
        idx += 1
        body = match.group("body")
        tool_name_match = re.search(r"<invoke_name>(.*?)</invoke_name>", body, re.S)
        params_match = re.search(r"<parameters>(.*?)</parameters>", body, re.S)
        if not tool_name_match:
            continue
        tool_name = tool_name_match.group(1).strip()
        args = parse_simple_args(params_match.group(1)) if params_match else {}
        tool_calls.append({"type": "tool_use", "id": f"dsml-{tool_name}-{idx}", "name": tool_name, "input": args})

    # Deepseek DSML inline invocation format
    dsml_invoke_re = re.compile(r'<[^>]*?invoke\s+name="(?P<tool>[^"]+)"[^>]*>(?P<body>.*?)</[^>]*?invoke[^>]*>', re.S)
    for match in dsml_invoke_re.finditer(text):
        idx += 1
        tool_name = match.group("tool").strip()
        args = parse_parameters(match.group("body"))
        tool_calls.append({"type": "tool_use", "id": f"dsml-{tool_name}-{idx}", "name": tool_name, "input": args})

    # Fallback plain XML-style tool tags
    for match in re.finditer(r"<(?P<tool>[^>\s]+)>\s*(?P<body>.*?)\s*</(?P=tool)>", text, re.S):
        tool_name = match.group("tool")
        body = match.group("body").strip()
        if tool_name in ("react_task_invoke", "tool_calls") or "DSML" in tool_name or "antartifact" in tool_name:
            continue
        idx += 1
        args = parse_simple_args(body)
        if not args and body:
            args = {"input": body}
        tool_calls.append({"type": "tool_use", "id": f"dsml-{tool_name}-{idx}", "name": tool_name, "input": args})

    return tool_calls


def run_agent() -> None:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("ERROR: 環境変数 DEEPSEEK_API_KEY が設定されていません。", file=sys.stderr)
        sys.exit(1)

    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        print("WARNING: GITHUB_TOKEN が未設定です。GitHub API のレート制限が厳しくなります。")

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )

    print("=" * 60)
    print("Investigation Agent 起動")
    print(f"モデル : {MODEL}")
    print(f"GitHub : {'認証あり' if github_token else '未認証（レート制限注意）'}")
    print("=" * 60)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": INITIAL_PROMPT}
    ]

    turn = 0
    while turn < MAX_TURNS:
        turn += 1
        print(f"\n[Turn {turn}] Deepseek に送信中...", flush=True)

        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=messages,
        )

        # Get first choice
        choice = response.choices[0]
        stop_reason = choice.finish_reason

        # Show stop reason
        print(f"  finish_reason: {stop_reason}")

        # Process message content
        if choice.message.content:
            preview = choice.message.content[:200].replace("\n", " ")
            print(f"  [TEXT] {preview}{'...' if len(choice.message.content) > 200 else ''}")

        # Collect tool calls
        tool_calls = []
        if hasattr(choice.message, 'tool_calls') and choice.message.tool_calls is not None:
            tool_calls = choice.message.tool_calls
        else:
            dsml_calls = parse_dsml_tool_calls(choice.message.content or "")
            if dsml_calls:
                tool_calls = dsml_calls

        if tool_calls:
            for tool_call in tool_calls:
                if hasattr(tool_call, 'function'):
                    args_preview = str(tool_call.function.arguments)[:120]
                    print(f"  [TOOL] {tool_call.function.name}({args_preview})")
                else:
                    args_preview = str(tool_call['input'])[:120]
                    print(f"  [TOOL] {tool_call['name']}({args_preview})")

        # Finished
        if stop_reason == "stop" and not tool_calls:
            if turn < MAX_TURNS:
                print("  [NOTE] stop_reason stop without tool calls; continuing調査を続行します。")
                messages.append({"role": "assistant", "content": choice.message.content or ""})
                messages.append({"role": "user", "content": "調査を続行し、必要なツールを使用してください。"})
                continue
            print("\n調査完了。")
            break

        # Execute tools
        if tool_calls:
            # Convert tool_calls to anthropic-like format for execute_tools
            tool_use_blocks = []
            import json
            for tc in tool_calls:
                if isinstance(tc, dict):
                    args = dict(tc["input"])
                    tool_name = tc["name"]

                    # Common Deepseek DSML param variants
                    if tool_name == "list_files" or tool_name == "list_folder_structure":
                        tool_name = "list_files"
                        if "path" in args:
                            args["directory"] = args.pop("path")
                        if "filePath" in args:
                            args["directory"] = args.pop("filePath")
                        if "item" in args:
                            args["directory"] = args.pop("item")
                        if "target" in args:
                            args["directory"] = args.pop("target")
                        if "dir" in args:
                            args["directory"] = args.pop("dir")
                        if "dir_path" in args:
                            args["directory"] = args.pop("dir_path")
                        if "folder_path" in args:
                            args["directory"] = args.pop("folder_path")
                        if "directory" in args and isinstance(args["directory"], bool):
                            args.pop("directory", None)

                    if tool_name == "read_file":
                        if "filePath" in args:
                            args["path"] = args.pop("filePath")
                        if "file_path" in args:
                            args["path"] = args.pop("file_path")

                    if tool_name == "search_code":
                        # Accept various Deepseek synonyms: regex -> pattern, path -> root
                        if "keyword" in args:
                            args["pattern"] = args.pop("keyword")
                        if "regex" in args:
                            args["pattern"] = args.pop("regex")
                        if "pattern" in args and isinstance(args["pattern"], dict) and "value" in args["pattern"]:
                            # handle nested parameter encodings
                            args["pattern"] = args["pattern"]["value"]
                        if "path" in args:
                            args["root"] = args.pop("path")
                        if "filePath" in args:
                            args["root"] = args.pop("filePath")
                        if "directory" in args:
                            args["root"] = args.pop("directory")
                        # file glob / pattern synonyms
                        for k in ("file_glob", "fileGlob", "glob", "filepattern", "filePattern", "fileGlobPattern", "file"):
                            if k in args and "file_glob" not in args:
                                args["file_glob"] = args.pop(k)

                    if tool_name == "get_github_issues":
                        if "repo_name" in args:
                            args["repo"] = args.pop("repo_name")
                        if "owner" in args and "repo" in args:
                            args["repo"] = f"{args.pop('owner')}/{args['repo']}"

                    if tool_name == "get_github_issue":
                        if "repo_name" in args:
                            args["repo"] = args.pop("repo_name")
                        if "owner" in args and "repo" in args:
                            args["repo"] = f"{args.pop('owner')}/{args['repo']}"

                    # write_report: normalize multiple possible param names; prefer `content`
                    if tool_name == "write_report":
                        if "markdown" in args:
                            args["content"] = args.pop("markdown")
                        if "text" in args:
                            args["content"] = args.pop("text")
                        if "file_path" in args and "content" not in args:
                            # attempt to load content from given path when content missing
                            try:
                                from pathlib import Path as _P
                                pth = _P(args.pop("file_path"))
                                if pth.exists():
                                    args["content"] = pth.read_text(encoding="utf-8")
                            except Exception:
                                pass
                        # remove any unrelated path-like keys to avoid unexpected kwargs
                        for rem in ("path", "file", "filepath", "filename", "output", "report", "pathname", "path_to_file"):
                            if rem in args:
                                args.pop(rem, None)

                    # Convert integer-like string parameters to ints (offset/limit/issue_number)
                    for int_key in ("offset", "limit", "issue_number", "issueNumber"):
                        if int_key in args and isinstance(args[int_key], str):
                            try:
                                args[int_key] = int(args[int_key])
                            except Exception:
                                pass

                    tool_use_blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tool_name,
                        "input": args,
                    })
                else:
                    tool_use_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.function.name,
                        "input": json.loads(tc.function.arguments)
                    })
            
            tool_results = execute_tools_openai(tool_use_blocks)

            # Show tool result previews
            for r in tool_results:
                preview = r["content"][:200].replace("\n", " ")
                print(f"  [RESULT] {preview}{'...' if len(r['content']) > 200 else ''}")

            # Add assistant message with tool_calls
            assistant_msg = {
                "role": "assistant",
                "content": choice.message.content or "",
                "tool_calls": []
            }
            for tc in tool_calls:
                if isinstance(tc, dict):
                    assistant_msg["tool_calls"].append({
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["input"])
                        }
                    })
                else:
                    assistant_msg["tool_calls"].append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })
            messages.append(assistant_msg)

            # Add tool results
            for r in tool_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": r["tool_use_id"],
                    "content": r["content"]
                })
        elif stop_reason == "length":
            # Continue: append what we have and let Deepseek finish
            if choice.message.content:
                messages.append({"role": "assistant", "content": choice.message.content})
            messages.append({"role": "user", "content": "続きを書いてください。write_report ツールでレポートを保存してください。"})
        else:
            print(f"予期しない finish_reason: {stop_reason}")
            break
    else:
        print(f"\nWARNING: ターン上限 ({MAX_TURNS}) に達しました。")

    print("\n" + "=" * 60)
    print("Investigation Agent 終了")
    print("=" * 60)


if __name__ == "__main__":
    run_agent()
