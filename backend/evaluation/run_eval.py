# -*- coding: utf-8 -*-
"""고정 평가셋(eval_cases.py)으로 자연어 레시피 검색 품질을 측정한다.

사용법:
    python evaluation/run_eval.py

임베딩 모델을 바꾸거나 레시피의 embedding_text를 고칠 때마다 이 스크립트를
돌려서, 특정 쿼리 하나만 눈으로 확인하는 대신 전체 평가셋 기준으로
좋아졌는지/나빠졌는지를 점수로 비교한다. 결과는 eval_history.jsonl에
타임스탬프와 함께 쌓여서, 시간이 지나며 점수가 어떻게 바뀌었는지 추적할 수 있다.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass  # 콘솔이 reconfigure를 지원하지 않으면 그냥 기본 인코딩으로 출력

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from crud.recipe import RecipeCrud
from service import reranker
from vectorstore import chroma_store
from evaluation.eval_cases import EVAL_CASES

HISTORY_PATH = Path(__file__).resolve().parent / "eval_history.jsonl"
TOP_K = 10


def _first_hit_rank(ranked_refs, acceptable_refs):
    """acceptable_refs 중 하나가 처음 등장하는 순위(1부터). 없으면 None."""
    acceptable = set(acceptable_refs)
    for rank, ref in enumerate(ranked_refs, start=1):
        if ref in acceptable:
            return rank
    return None


def run():
    results = []
    for case in EVAL_CASES:
        ranked_refs = chroma_store.search(case["query"], n_results=TOP_K)
        candidates = [RecipeCrud.get_by_ref(ref) for ref in ranked_refs]
        candidates = [c for c in candidates if c is not None]
        candidates = reranker.rerank(case["query"], candidates)
        reranked_refs = [c["recipe_ref"] for c in candidates]

        rank = _first_hit_rank(reranked_refs, case["acceptable_refs"])
        results.append(
            {
                "query": case["query"],
                "note": case["note"],
                "rank": rank,
                "top1": reranked_refs[0] if reranked_refs else None,
            }
        )

    n = len(results)
    hit_at = {k: sum(1 for r in results if r["rank"] is not None and r["rank"] <= k) for k in (1, 3, 5, 10)}
    mrr = sum((1 / r["rank"]) if r["rank"] else 0 for r in results) / n

    print(f"임베딩 모델: {settings.embedding_model} (재랭킹 적용)\n")
    print(f"{'결과':4}  {'순위':4}  쿼리 (1위로 나온 레시피)")
    print("-" * 70)
    for r in results:
        status = "PASS" if r["rank"] == 1 else ("HIT " if r["rank"] else "FAIL")
        rank_str = str(r["rank"]) if r["rank"] else "-"
        print(f"[{status}] {rank_str:>4}  {r['query']}  -> {r['top1']}")

    print("-" * 70)
    for k in (1, 3, 5, 10):
        print(f"Hit@{k:<2}: {hit_at[k]}/{n} ({hit_at[k] / n:.0%})")
    print(f"MRR   : {mrr:.3f}")

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "embedding_model": settings.embedding_model,
                    "reranked": True,
                    "n_cases": n,
                    "hit_at_1": hit_at[1] / n,
                    "hit_at_3": hit_at[3] / n,
                    "hit_at_5": hit_at[5] / n,
                    "hit_at_10": hit_at[10] / n,
                    "mrr": mrr,
                    "per_case": [{"query": r["query"], "rank": r["rank"], "top1": r["top1"]} for r in results],
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    print(f"\n히스토리 기록: {HISTORY_PATH}")


if __name__ == "__main__":
    run()
