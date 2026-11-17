"""확대 평가셋(queries.jsonl)으로 검색 구성을 비교한다.

    python run_eval.py dev            # 개발용: 구성을 고르는 데 쓴다
    python run_eval.py test           # 최종용: 구성을 정한 뒤 한 번만 돌린다

LLM 결과는 cache/llm_results.json 에 쌓아서 다시 돌려도 호출 비용이 중복되지 않는다.
LLM 호출은 reasoning_effort="minimal" 로 고정했다 (12쿼리 파일럿에서 기본 설정과 같은 점수, 출력 토큰 약 1/25).
"""
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor

import core
from core import Index, first_hit_rank, summarize
from recipes import load_recipes

CACHE = core.CACHE_DIR / "llm_results.json"
_orig_chat = core.chat_json


def _minimal(system, user, model=core.DEFAULT_LLM, kind="llm", **extra):
    return _orig_chat(system, user, model, kind, reasoning_effort="minimal", **extra)


core.chat_json = _minimal

POOL_MAX = 20


def pooled(index: Index, query: str) -> list[str]:
    """여러 경로(벡터+카테고리 필터, 키워드)의 후보를 번갈아 담아 한 풀로 합친다."""
    v = index.vector_search(query, 10, use_filter=True)
    b = index.bm25_search(query, 10)
    out: list[str] = []
    for pair in zip(v + [None] * 10, b + [None] * 10):
        for r in pair:
            if r and r not in out:
                out.append(r)
    return out[:POOL_MAX]


def rrf(index: Index, query: str, k: int = 10) -> list[str]:
    lists = [index.vector_search(query, 30, use_filter=True), index.bm25_search(query, 30)]
    score: dict[str, float] = {}
    for lst in lists:
        for rank, r in enumerate(lst, start=1):
            score[r] = score.get(r, 0.0) + 1.0 / (60 + rank)
    return [r for r, _ in sorted(score.items(), key=lambda x: -x[1])][:k]


# ---- 구성 정의: 이름 -> (설명, 후보 함수, LLM 방식 또는 None)
CONFIGS = {
    "C1 벡터만": ("벡터 유사도 top-10", lambda ix, q: ix.vector_search(q, 10, use_filter=False), None),
    "C2 벡터+카테고리 필터": ("원본 search() 와 동일, 재랭킹 전", lambda ix, q: ix.vector_search(q, 10, True), None),
    "C3 키워드(BM25)만": ("2글자 조각 BM25 top-10", lambda ix, q: ix.bm25_search(q, 10), None),
    "C4 하이브리드(RRF)": ("벡터+필터, BM25 순위 합산 top-10 (LLM 없음)", lambda ix, q: rrf(ix, q, 10), None),
    "C5 원본(필터→LLM 재랭킹)": ("현재 서비스 구성", lambda ix, q: ix.vector_search(q, 10, True), "listwise"),
    "C6 후보 풀→LLM 재랭킹": ("벡터·키워드 후보를 합친 풀을 LLM이 재랭킹", pooled, "listwise"),
    "C7 후보 풀→LLM 점수": ("같은 풀을 LLM이 0~10점으로 채점", pooled, "score"),
}


def load_cache() -> dict:
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def run_split(split: str) -> dict:
    rows = [json.loads(l) for l in open(core.HERE / "queries.jsonl", encoding="utf-8")]
    rows = [r for r in rows if r["split"] == split]
    index = Index(load_recipes())
    cache = load_cache()
    results: dict[str, dict] = {}

    for name, (desc, cand_fn, mode) in CONFIGS.items():
        def one(row):
            cands = cand_fn(index, row["query"])
            if mode is None:
                return cands, cands
            key = f"{name}|{row['query']}"
            if key not in cache:
                fn = core.rerank_listwise if mode == "listwise" else core.score_pointwise
                cache[key] = fn(index, row["query"], cands)
            return cands, cache[key]

        if mode is None:
            outs = [one(r) for r in rows]
        else:
            with ThreadPoolExecutor(8) as ex:
                outs = list(ex.map(one, rows))
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        ranks = [first_hit_rank(final, {r["gold"]}) for (_, final), r in zip(outs, rows)]
        pool_recall = sum(1 for (cands, _), r in zip(outs, rows) if r["gold"] in cands) / len(rows)
        s = summarize(ranks)
        s["pool_recall"] = round(pool_recall, 3)
        s["pool_size"] = round(sum(len(c) for c, _ in outs) / len(outs), 1)
        s["ranks"] = ranks
        results[name] = s
    return results


def sign_test(a: list, b: list) -> tuple[int, int, float]:
    """두 구성의 1위 적중을 쿼리별로 비교 (a 보다 b 가 나은 쿼리 수, 못한 쿼리 수, 양측 정확검정 p)."""
    win = sum(1 for x, y in zip(a, b) if (y == 1) and (x != 1))
    loss = sum(1 for x, y in zip(a, b) if (x == 1) and (y != 1))
    n = win + loss
    if n == 0:
        return 0, 0, 1.0
    k = min(win, loss)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(0, k + 1)) / 2**n)
    return win, loss, p


def show(split: str, results: dict) -> None:
    n = next(iter(results.values()))["n"]
    print(f"\n=== {split} ({n}개 쿼리, 정답 레시피 1개, 95% 신뢰구간) ===")
    print(f"{'구성':26} {'Hit@1':>16} {'Hit@3':>8} {'Hit@10':>8} {'MRR':>6} {'후보에 정답':>10}")
    for name, s in results.items():
        h1 = s["hit@1"]
        print(f"{name:26} {h1[0]:>3}/{n} {h1[1]:.0%} [{h1[2]:.0%}~{h1[3]:.0%}] {s['hit@3'][1]:>7.0%} {s['hit@10'][1]:>8.0%} {s['mrr']:>6} {s['pool_recall']:>9.0%}")
    print(f"(무작위로 뽑으면 Hit@1 {1/110:.1%}, Hit@3 {3/110:.1%}, Hit@10 {10/110:.1%})")
    base = results["C5 원본(필터→LLM 재랭킹)"]["ranks"]
    print("\n원본(C5)과 1위 적중 쿼리 수 비교 (더 나음 / 더 나쁨 / 부호검정 p):")
    for name, s in results.items():
        if name.startswith("C5"):
            continue
        w, l, p = sign_test(base, s["ranks"])
        print(f"  {name:26} {w:>3} / {l:>3}   p={p:.3f}")


if __name__ == "__main__":
    split = sys.argv[1] if len(sys.argv) > 1 else "dev"
    res = run_split(split)
    show(split, res)
    (core.HERE / f"results_{split}.json").write_text(
        json.dumps({k: {x: y for x, y in v.items() if x != "ranks"} for k, v in res.items()}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print("\n누적 사용량:", {k: v for k, v in core.ledger_summary().items() if not k.startswith("embedding")})
