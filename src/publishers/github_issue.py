"""承認 Issue — スマホからの唯一の操作面。

通勤中に触れるのは GitHub モバイルアプリだけ、という前提で設計している。
毎朝 cron が生成物を 1 通の Issue にまとめ、ユーザーはコメントで承認する。

  /approve <item_id>          承認
  /reject  <item_id> [理由]   却下
  /approve all                未処理を一括承認（safety_flags 付きは除外）
  /status                     キュー状況を返信
  /revenue <金額> <ASP名> [メモ]  収益を記録
  /adopt   <opportunity_id>   探索レイヤのネタを採用して制作を始める（確信度でレベル自動判定）
  /test    <opportunity_id>   小さく試す（CHEAP_TEST）。少ない本数で実データを取る
  /scale   <opportunity_id>   生成枠を増やす（SCALE）
  /drop    <opportunity_id>   そのネタを捨てる
  /m <niche> <累計views> <累計revenue>
                              実績を記録してファネル段階を診断する（/metrics も同じ）
                              投稿数は自動。1つだけなら `/m <niche> <revenue>` でよい

`GITHUB_TOKEN` が無い環境（ローカル）では API を呼ばず Markdown を返すだけ。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import requests

from ..config import Config
from ..publishers.review_queue import ReviewItem

logger = logging.getLogger(__name__)

API_ROOT = "https://api.github.com"
COMMAND_RE = re.compile(
    r"^\s*/(approve|reject|status|revenue|adopt|drop|metrics|m|test|scale)\b[ \t]*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class Command:
    """コメントから抽出した 1 コマンド。"""

    action: str            # approve|reject|status|revenue|adopt|test|scale|drop|metrics
    target: str = ""       # item_id または "all"
    note: str = ""         # 却下理由 / 収益のメモ


def parse_commands(comment_body: str) -> list[Command]:
    """コメント本文からコマンドを抽出する。1コメントに複数行書いても全部拾う。"""
    commands: list[Command] = []
    for action, rest in COMMAND_RE.findall(comment_body or ""):
        action = "metrics" if action.lower() == "m" else action.lower()
        rest = rest.strip()
        if action == "status":
            commands.append(Command(action="status"))
            continue
        if not rest:
            logger.warning("引数のないコマンドを無視します: /%s", action)
            continue
        target, _, note = rest.partition(" ")
        commands.append(Command(action=action, target=target.strip(), note=note.strip()))
    return commands


def render_approval_issue(items: list[tuple[ReviewItem, dict]]) -> str:
    """承認 Issue の本文を組む。

    items は (ReviewItem, article_dict) の組。article_dict は記事の to_dict()。
    通勤中に読める密度に抑えるため、台本と記事本文は <details> で畳む。
    """
    if not items:
        return "本日の生成結果はありません（収集条件に合う話題がなかった可能性があります）。"

    header = [
        "今朝の生成結果です。コメントで承認してください。",
        "",
        "```",
        "/approve <id>            承認",
        "/reject  <id> 理由        却下",
        "/approve all             未処理を一括承認（⚠️付きは対象外）",
        "/status                  キュー状況",
        "```",
        "",
        "確認するのは **①⚠️フラグ ②換金経路 ③タイトルが事実として正しいか** の3点だけで足ります。",
        "",
        "---",
        "",
    ]

    body: list[str] = []
    for item, article in items:
        script = item.script
        flags = item.safety_flags
        flag_text = ("⚠️ " + ", ".join(flags)) if flags else "なし"
        route = article.get("monetization_route", "なし")
        route_text = route if route != "なし" else "⚠️ なし（AFF_* Secrets を確認）"
        gen = script.get("generated_by", "template")
        gen_text = "Claude" if gen == "claude" else "⚠️ テンプレ（ANTHROPIC_API_KEY 未設定）"

        body.extend([
            f"### `{item.id}`",
            "",
            f"**タイトル**: {script.get('title', '(なし)')}",
            f"**フック**: {script.get('hook', '(なし)')}",
            f"**換金経路**: {route_text}",
            f"**safety_flags**: {flag_text}",
            f"**生成**: {gen_text} / スライド {len(script.get('slides', []))}枚",
            "",
            "<details><summary>台本を開く</summary>",
            "",
        ])
        for i, (slide, narration) in enumerate(
            zip(script.get("slides", []), script.get("narration", [])), start=1
        ):
            body.append(f"{i}. **{slide}**  \n   {narration}")
        body.extend([
            "",
            "**投稿説明文**",
            "",
            "```",
            script.get("description", ""),
            "```",
            "",
            "</details>",
            "",
            "<details><summary>記事下書きを開く</summary>",
            "",
            article.get("body_markdown", "(記事なし)"),
            "",
            "</details>",
            "",
            f"承認: `/approve {item.id}` ／ 却下: `/reject {item.id} 理由`",
            "",
            "---",
            "",
        ])

    return "\n".join(header + body)


class GitHubIssueSurface:
    """Issue の作成・コメント。GITHUB_TOKEN が無い場合は何もしない（ログのみ）。"""

    def __init__(self, config: Config):
        self.token = config.github_token
        self.repo = config.github_repository
        self.label = config.section("approval").get("label", "approval-queue")

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.repo)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def create_issue(self, title: str, body: str) -> dict:
        if not self.enabled:
            logger.info("GITHUB_TOKEN/GITHUB_REPOSITORY 未設定のため Issue を作成しません。")
            return {"skipped": True, "title": title, "body": body}

        resp = requests.post(
            f"{API_ROOT}/repos/{self.repo}/issues",
            headers=self._headers(),
            json={"title": title, "body": body, "labels": [self.label]},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info("承認 Issue を作成しました: #%s", data.get("number"))
        return data

    def comment(self, issue_number: int, body: str) -> dict:
        if not self.enabled:
            logger.info("[skip] Issue #%s へのコメント:\n%s", issue_number, body)
            return {"skipped": True, "body": body}

        resp = requests.post(
            f"{API_ROOT}/repos/{self.repo}/issues/{issue_number}/comments",
            headers=self._headers(),
            json={"body": body},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
