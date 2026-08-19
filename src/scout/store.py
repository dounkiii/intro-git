"""探索結果の永続化と重複排除。

DB は使わない。JSONL + git で足りる（履歴と監査ログが無料で付く上、Actions の
ランナーが破棄されても状態が残る）。Notion / Sheets / SQLite は MVP には過剰。

重複排除の方針がちゃっぴー案と違う点:
  「同じネタは捨てる」ではなく **統合して観測回数と伸びを追跡する**。
  3日連続で出てきて伸びているネタは、初出のネタより有望である可能性が高い。
  逆に何度も出るのに伸びないネタは陳腐化として scoring 側で減点する。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from ..config import DATA_DIR
from .models import Candidate, Opportunity, normalize_tokens

logger = logging.getLogger(__name__)

SCOUT_DIR = DATA_DIR / "scout"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class OpportunityStore:
    def __init__(self, directory: Path = SCOUT_DIR):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "opportunities.jsonl"

    # ------------------------------------------------------------------
    def load_all(self) -> list[Opportunity]:
        if not self.path.exists():
            return []
        items: list[Opportunity] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(Opportunity.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("読み飛ばした行があります: %s", exc)
        return items

    def save_all(self, items: list[Opportunity]) -> None:
        """全件書き戻す。件数は日次で数十件のオーダーなので追記管理より単純さを取る。"""
        self.path.write_text(
            "\n".join(json.dumps(i.to_dict(), ensure_ascii=False) for i in items) + "\n",
            encoding="utf-8",
        )

    def get(self, opportunity_id: str) -> Opportunity | None:
        return next((o for o in self.load_all() if o.id == opportunity_id), None)

    def set_status(self, opportunity_id: str, status: str) -> Opportunity | None:
        items = self.load_all()
        target = next((o for o in items if o.id == opportunity_id), None)
        if target is None:
            return None
        target.status = status
        self.save_all(items)
        return target

    # ------------------------------------------------------------------
    def merge(self, candidates: list[Candidate], similarity: float = 0.6
              ) -> tuple[list[tuple[Candidate, int]], list[Opportunity]]:
        """既存ネタと突き合わせる。

        戻り値は (調査すべき候補と観測回数, 既存で観測回数だけ増えたもの)。
        `similarity` は Jaccard 係数の閾値。
        """
        existing = self.load_all()
        by_id = {o.id: o for o in existing}
        fresh: list[tuple[Candidate, int]] = []
        touched: list[Opportunity] = []
        seen_this_run: set[str] = set()

        for candidate in candidates:
            match = self._find_match(candidate, existing, similarity)

            if match is None:
                if candidate.slug in seen_this_run:
                    continue   # 同一実行内の重複
                seen_this_run.add(candidate.slug)
                fresh.append((candidate, 1))
                continue

            # 既存ネタ: 観測回数を増やし、シグナルは新しい方で上書きする
            match.times_seen += 1
            match.last_seen = _now()
            if candidate.signals:
                match.candidate.signals = candidate.signals
            for url in candidate.evidence_urls:
                if url not in match.candidate.evidence_urls:
                    match.candidate.evidence_urls.append(url)

            # 「捨てる」判定済みのものは再調査しない（毎日同じものを見せないため）
            if match.status == "dropped" or match.verdict == "drop":
                touched.append(match)
                continue

            fresh.append((candidate, match.times_seen))
            touched.append(match)

        if touched:
            self.save_all(list(by_id.values()))
        return fresh, touched

    @staticmethod
    def _find_match(candidate: Candidate, existing: list[Opportunity],
                    similarity: float) -> Opportunity | None:
        slug = candidate.slug
        tokens = normalize_tokens(candidate.title, " ".join(candidate.keywords))
        best: tuple[float, Opportunity] | None = None

        for item in existing:
            if item.id == slug:
                return item
            other = normalize_tokens(item.candidate.title,
                                     " ".join(item.candidate.keywords))
            if not tokens or not other:
                continue
            score = len(tokens & other) / len(tokens | other)
            if score >= similarity and (best is None or score > best[0]):
                best = (score, item)

        return best[1] if best else None

    # ------------------------------------------------------------------
    def upsert(self, opportunity: Opportunity) -> Opportunity:
        """1件を追加または更新する。"""
        items = self.load_all()
        for i, existing in enumerate(items):
            if existing.id == opportunity.id:
                opportunity.first_seen = existing.first_seen or _now()
                opportunity.last_seen = _now()
                items[i] = opportunity
                self.save_all(items)
                return opportunity

        opportunity.first_seen = opportunity.first_seen or _now()
        opportunity.last_seen = _now()
        items.append(opportunity)
        self.save_all(items)
        return opportunity
