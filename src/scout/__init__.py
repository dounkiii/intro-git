"""探索レイヤ（リサーチ → 評価 → 収益化案）。

制作レイヤ（src/pipeline.py）とは data/adopted_niches.yaml で接続している。
設計の意図とちゃっぴー案からの変更点は docs/RESEARCH_SYSTEM.md。
"""
from .models import Candidate, Opportunity, Research, Score
from .niches import Niche, NicheRegistry
from .runner import ScoutPipeline
from .store import OpportunityStore

__all__ = ["Candidate", "Opportunity", "Research", "Score", "Niche",
           "NicheRegistry", "ScoutPipeline", "OpportunityStore"]
