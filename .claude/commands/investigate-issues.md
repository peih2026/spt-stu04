---
description: poc-investigation-targets の GitHub Issues を取得・分析し、調査レポート（Markdown + PDF）を生成する。引数なしで即時実行、--at HH:MM で定時スケジュール登録。
argument-hint: "[--at HH:MM]"
---

# GitHub Issue 調査 Skill

引数 `$ARGUMENTS` を確認し、以下のいずれかを実行してください。

---

## ケース A: `--at` が指定されている場合 → スケジュール登録

`$ARGUMENTS` に `--at HH:MM` パターンが含まれる場合:

1. `--at HH:MM` から時刻を取り出して Cron 式に変換する
   - 例: `--at 07:00` → `0 7 * * *`
   - 例: `--at 09:30` → `30 9 * * *`

2. `/schedule` Skill を使って以下の内容でスケジュールを登録する:
   - **実行内容**: `python agent.py` を実行して調査レポートを生成する
   - **Cron**: 変換した Cron 式
   - **作業ディレクトリ**: このファイルが置かれている `investigation-agent/` ディレクトリ
   - **説明**: "poc-investigation-targets 調査レポート 日次自動生成"

3. 登録完了後、以下を表示する:
   - 登録されたスケジュール名と Cron 式
   - 次回実行予定日時

---

## ケース B: `--at` が指定されていない場合 → 即時実行

1. 環境変数を確認する:
   - `GITHUB_TOKEN` が設定されているか確認（未設定の場合は警告を表示）
   - `ANTHROPIC_API_KEY` が設定されているか確認（未設定の場合はエラーで停止）

2. 以下のコマンドを実行する:
   ```
   python agent.py
   ```

3. 実行完了後、以下を表示する:
   - 生成された Markdown レポートのパス
   - 生成された PDF レポートのパス
   - レポート内の「エグゼクティブサマリー」セクションの内容

---

## 前提条件

- このコマンドは `investigation-agent/` ディレクトリで Claude Code を起動した状態で使用すること
- `pip install -r requirements.txt` が完了していること
- `ANTHROPIC_API_KEY` 環境変数が設定されていること
- `GITHUB_TOKEN` 環境変数が設定されていること（未設定でも動作するが GitHub API レート制限が厳しくなる）

---

## 使い方

```bash
# 即時実行
/investigate-issues

# 毎日 07:00 に定時実行するスケジュールを登録
/investigate-issues --at 07:00

# 平日 09:00 のみ実行
/investigate-issues --at 09:00
```
