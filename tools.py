# -*- coding: utf-8 -*-
"""Tool implementations for the investigation agent."""

import os
import re
import fnmatch
import requests
from pathlib import Path

GITHUB_REPO = "baoshi1970/poc-investigation-targets"
GITHUB_API  = "https://api.github.com"


# ---------------------------------------------------------------------------
# Tool schemas (passed to Claude API)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "list_files",
        "description": "ディレクトリ以下のファイルを再帰的にリストする。.git/ は自動除外。",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "検索対象ディレクトリの絶対パス"
                },
                "extension_filter": {
                    "type": "string",
                    "description": "拡張子フィルタ（例: .java, .xml, .sql）。省略時は全ファイル"
                }
            },
            "required": ["directory"]
        }
    },
    {
        "name": "read_file",
        "description": "ファイルの内容を読み込む。大きなファイルは offset / limit で分割読込可能。",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "読み込むファイルの絶対パス"
                },
                "offset": {
                    "type": "integer",
                    "description": "読み始める行番号（0始まり）。デフォルト 0",
                    "default": 0
                },
                "limit": {
                    "type": "integer",
                    "description": "読み込む最大行数。デフォルト 200",
                    "default": 200
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "search_code",
        "description": "ディレクトリ以下のファイルからキーワード（正規表現）を検索する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "root": {
                    "type": "string",
                    "description": "検索対象のルートディレクトリ"
                },
                "pattern": {
                    "type": "string",
                    "description": "検索する正規表現パターン"
                },
                "file_glob": {
                    "type": "string",
                    "description": "対象ファイルの glob パターン（例: *.java, *.xml）。省略時は全ファイル"
                }
            },
            "required": ["root", "pattern"]
        }
    },
    {
        "name": "get_github_issues",
        "description": f"GitHub リポジトリ ({GITHUB_REPO}) の Issue 一覧を取得する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "description": "取得する Issue の状態。デフォルト all",
                    "default": "all"
                },
                "repo": {
                    "type": "string",
                    "description": "GitHub リポジトリ名（owner/repo）。省略時はデフォルトのリポジトリを使用します。"
                },
                "repo_name": {
                    "type": "string",
                    "description": "GitHub リポジトリ名（owner/repo）の別名。"
                },
                "owner": {
                    "type": "string",
                    "description": "GitHub リポジトリの所有者。repo と組み合わせて owner/repo を構成します。"
                }
            }
        }
    },
    {
        "name": "get_github_issue",
        "description": f"GitHub リポジトリ ({GITHUB_REPO}) の特定 Issue の詳細（本文＋コメント）を取得する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_number": {
                    "type": "integer",
                    "description": "取得する Issue 番号"
                },
                "repo": {
                    "type": "string",
                    "description": "GitHub リポジトリ名（owner/repo）。省略時はデフォルトのリポジトリを使用します。"
                },
                "repo_name": {
                    "type": "string",
                    "description": "GitHub リポジトリ名（owner/repo）の別名。"
                },
                "owner": {
                    "type": "string",
                    "description": "GitHub リポジトリの所有者。repo と組み合わせて owner/repo を構成します。"
                }
            },
            "required": ["issue_number"]
        }
    },
    {
        "name": "write_report",
        "description": "調査結果を Markdown レポートとして保存し、同時に PDF と HTML を生成する。最後に一度だけ呼ぶこと。",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "レポートの Markdown 本文（完全版）"
                }
            },
            "required": ["content"]
        }
    }
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def list_files(directory: str, extension_filter: str = None) -> str:
    root = Path(directory)
    if not root.exists():
        return f"ERROR: ディレクトリが存在しません: {directory}"

    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Exclude .git and __pycache__
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", "node_modules")]
        for fname in filenames:
            if extension_filter and not fname.endswith(extension_filter):
                continue
            full = Path(dirpath) / fname
            results.append(str(full))

    if not results:
        return f"(ファイルが見つかりませんでした: {directory}, filter={extension_filter})"
    return "\n".join(results)


def read_file(path: str, offset: int = 0, limit: int = 200) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        total = len(lines)
        chunk = lines[offset: offset + limit]
        header = f"[{path}  行 {offset+1}–{offset+len(chunk)} / 全{total}行]\n"
        return header + "".join(chunk)
    except FileNotFoundError:
        return f"ERROR: ファイルが見つかりません: {path}"
    except Exception as e:
        return f"ERROR: {e}"


def search_code(root: str, pattern: str, file_glob: str = None) -> str:
    results = []
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"ERROR: 正規表現エラー: {e}"

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
        for fname in filenames:
            if file_glob and not fnmatch.fnmatch(fname, file_glob):
                continue
            fpath = Path(dirpath) / fname
            try:
                with open(fpath, encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if regex.search(line):
                            results.append(f"{fpath}:{lineno}: {line.rstrip()}")
            except Exception:
                continue

    if not results:
        return f"(マッチなし: pattern={pattern}, root={root})"
    return "\n".join(results[:200])  # cap at 200 matches


def get_github_issues(state: str = "all", repo: str = None, owner: str = None, repo_name: str = None) -> str:
    if repo_name:
        repo = repo_name
    if owner and repo:
        repo = f"{owner}/{repo}"
    if not repo:
        repo = GITHUB_REPO

    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    issues = []
    page = 1
    while True:
        url = f"{GITHUB_API}/repos/{repo}/issues"
        resp = requests.get(url, headers=headers,
                            params={"state": state, "per_page": 100, "page": page},
                            timeout=30)
        if resp.status_code != 200:
            return f"ERROR: GitHub API {resp.status_code}: {resp.text[:300]}"
        batch = resp.json()
        if not batch:
            break
        # Exclude pull requests
        issues += [i for i in batch if "pull_request" not in i]
        page += 1

    if not issues:
        return "(Issues が見つかりませんでした)"

    lines = [f"取得件数: {len(issues)} 件\n"]
    for i in issues:
        lines.append(
            f"#{i['number']} [{i['state'].upper()}] {i['title']}\n"
            f"  Labels: {', '.join(l['name'] for l in i.get('labels', []))}\n"
            f"  Created: {i['created_at'][:10]}  Updated: {i['updated_at'][:10]}\n"
        )
    return "\n".join(lines)


def get_github_issue(issue_number: int, repo: str = None, owner: str = None, repo_name: str = None) -> str:
    if repo_name:
        repo = repo_name
    if owner and repo:
        repo = f"{owner}/{repo}"
    if not repo:
        repo = GITHUB_REPO

    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # Issue body
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}"
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        return f"ERROR: {resp.status_code}: {resp.text[:300]}"
    issue = resp.json()

    # Comments
    c_url = f"{GITHUB_API}/repos/{GITHUB_REPO}/issues/{issue_number}/comments"
    c_resp = requests.get(c_url, headers=headers, timeout=30)
    comments = c_resp.json() if c_resp.status_code == 200 else []

    out = [
        f"# Issue #{issue_number}: {issue['title']}",
        f"State: {issue['state']}",
        f"Labels: {', '.join(l['name'] for l in issue.get('labels', []))}",
        f"Created: {issue['created_at'][:10]}",
        f"\n## 本文\n{issue.get('body') or '(本文なし)'}",
    ]
    if comments:
        out.append(f"\n## コメント ({len(comments)} 件)")
        for c in comments:
            out.append(f"\n**{c['user']['login']}** ({c['created_at'][:10]}):\n{c.get('body','')}")
    return "\n".join(out)


def write_report(content: str) -> str:
    from report_writer import write_report as _write
    md_path, pdf_path, html_path = _write(content)
    return (
        f"レポートを保存しました:\n"
        f"  Markdown: {md_path}\n"
        f"  PDF:      {pdf_path}\n"
        f"  HTML:     {html_path}"
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def execute_tools(tool_use_blocks: list) -> list:
    """Execute all tool_use blocks and return tool_result list."""
    results = []
    for block in tool_use_blocks:
        if block.type != "tool_use":
            continue
        name  = block.name
        args  = block.input
        try:
            if name == "list_files":
                output = list_files(**args)
            elif name == "read_file":
                output = read_file(**args)
            elif name == "search_code":
                output = search_code(**args)
            elif name == "get_github_issues":
                output = get_github_issues(**args)
            elif name == "get_github_issue":
                output = get_github_issue(**args)
            elif name == "write_report":
                output = write_report(**args)
            else:
                output = f"ERROR: 未知のツール: {name}"
        except Exception as e:
            output = f"ERROR ({name}): {e}"

        results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": output,
        })
    return results
