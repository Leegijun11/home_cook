"""패치한 서비스 코드(chroma_store.search_pooled, reranker.rerank)가 평가 도구와 같은 결과를 내는지 확인한다."""
import json
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]

os.environ["OPENAI_API_KEY"] = dotenv_values(BACKEND / ".env")["OPENAI_API_KEY"]
os.environ["DATABASE_URL"] = "sqlite://"  # 검색·재랭킹은 DB를 쓰지 않는다 (설정 항목만 채움)

sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(HERE))

import core  # noqa: E402  (평가 도구)
from recipes import load_recipes  # noqa: E402
from run_eval import pooled  # noqa: E402
from service import reranker  # noqa: E402  (서비스 코드)
from vectorstore import chroma_store  # noqa: E402  (서비스 코드)

recipes = load_recipes()
n = chroma_store.rebuild_index(recipes)
print("서비스 색인 레시피 수:", n)

index = core.Index(recipes)
rows = [json.loads(l) for l in open(HERE / "queries.jsonl", encoding="utf-8")]

same = diff_vec = diff_kw = 0
examples = []
for r in rows:
    q = r["query"]
    prod = chroma_store.search_pooled(q)
    mine = pooled(index, q)
    if prod == mine:
        same += 1
    else:
        if chroma_store.search(q, 10) != index.vector_search(q, 10, True):
            diff_vec += 1
        if chroma_store.keyword_search(q, 10) != index.bm25_search(q, 10):
            diff_kw += 1
        if len(examples) < 3:
            examples.append((q, prod[:6], mine[:6]))
print(f"후보 풀이 평가 도구와 완전히 같은 쿼리: {same}/{len(rows)}")
print(f"  벡터 후보 순서가 다른 쿼리 {diff_vec}, 키워드 후보 순서가 다른 쿼리 {diff_kw}")
for e in examples:
    print("  예:", e)

# 수정한 재랭커가 실제로 동작하는지 (예외가 나면 원래 순서를 그대로 돌려주므로, 순서가 바뀌었는지 본다)
test = [r for r in rows if r["split"] == "test"][:30]
changed = hit1 = 0
for r in test:
    refs = chroma_store.search_pooled(r["query"])
    cands = [index.by_ref[x] for x in refs]
    out = [c["recipe_ref"] for c in reranker.rerank(r["query"], cands)]
    changed += out != refs
    hit1 += out[0] == r["gold"]
print(f"수정한 재랭커: 30개 중 순서가 바뀐 쿼리 {changed}, 1위 적중 {hit1}")
print("옵션:", reranker._completion_options())
