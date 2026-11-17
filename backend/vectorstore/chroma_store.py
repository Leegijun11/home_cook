import math
import re
from collections import Counter
from pathlib import Path

import chromadb
from openai import OpenAI

from config import settings

CHROMA_DIR = Path(__file__).resolve().parent.parent / "chroma_db"
COLLECTION_NAME = "recipes"

client = OpenAI(api_key=settings.openai_api_key)
_chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))


def _embed(texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=settings.embedding_model, input=texts)
    return [item.embedding for item in response.data]


def _get_collection():
    return _chroma_client.get_or_create_collection(name=COLLECTION_NAME)


def rebuild_index(recipes: list[dict]) -> int:
    """recipes 전체를 받아 embedding_text가 있는 것만 다시 색인한다.

    컬렉션 자체를 지우고 새로 만든다 — 문서만 지우는 걸로는 부족하다. Chroma
    컬렉션은 처음 만들어질 때의 임베딩 차원이 고정되기 때문에, embedding_model을
    바꿔서 차원 수가 달라지면(예: small=1536, large=3072) 기존 컬렉션에 그냥
    넣으려고 할 때 InvalidArgumentError가 난다.
    """
    global _keyword_index
    _keyword_index = None  # 키워드 색인은 Chroma 에 저장된 문서에서 다시 만든다
    try:
        _chroma_client.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass  # 컬렉션이 아직 없으면 그냥 넘어감
    collection = _get_collection()

    targets = [r for r in recipes if r.get("embedding_text")]
    if not targets:
        return 0

    texts = [r["embedding_text"] for r in targets]
    vectors = _embed(texts)
    collection.add(
        ids=[r["recipe_ref"] for r in targets],
        embeddings=vectors,
        documents=texts,
        metadatas=[
            {
                "cuisine": r.get("cuisine") or "",
                "dish_type": r.get("dish_type") or "",
                "menu": r.get("name") or "",
            }
            for r in targets
        ],
    )
    return len(targets)


DISH_TYPE_KEYWORDS = {
    "국물/찌개류": ["국물", "찌개", "탕", "수프"],
    "면류": ["면", "국수", "파스타", "우동", "라멘"],
    "밥류": ["밥", "덮밥", "리조또"],
    "볶음류": ["볶음"],
    "구이류": ["구이", "꼬치", "스테이크"],
    "샐러드/간편식": ["샐러드", "무침", "반찬", "초밥", "간편식"],
}


def _detect_dish_types(query: str) -> list[str]:
    """쿼리에 카테고리를 암시하는 단어가 있으면 해당 dish_type들을 반환한다.

    벡터 유사도만 믿으면 "얼큰한 국물" 같은 쿼리에 국물이 아닌 반찬(양파무침 등)이
    끼어드는 문제가 있었다 — 쿼리가 카테고리를 직접 언급하면 그건 벡터보다 훨씬
    신뢰도 높은 신호이므로, 메타데이터로 먼저 걸러서 애초에 후보에 못 들어오게
    한다. 아무 카테고리 단어도 없으면 빈 리스트를 반환해 필터 없이 전체 검색한다.
    """
    return [
        dish_type
        for dish_type, keywords in DISH_TYPE_KEYWORDS.items()
        if any(keyword in query for keyword in keywords)
    ]


def search(query: str, n_results: int = 10) -> list[str]:
    """자연어 쿼리와 의미적으로 가까운 레시피를 유사도순 recipe_ref 리스트로 반환.

    쿼리에 카테고리 단서가 있으면 그 dish_type으로 먼저 좁힌 뒤 벡터 유사도로
    순위를 매긴다(메타데이터 필터 + 벡터 검색 하이브리드).
    """
    collection = _get_collection()
    if collection.count() == 0:
        return []

    vector = _embed([query])[0]
    dish_types = _detect_dish_types(query)
    where = {"dish_type": {"$in": dish_types}} if dish_types else None

    result = collection.query(query_embeddings=[vector], n_results=n_results, where=where)
    ids = result.get("ids") or []
    return ids[0] if ids else []


# ---------------------------------------------------------------- 키워드 검색 + 후보 풀
# 벡터 검색은 후보 10개 안에 정답이 절반도 안 들어오는 쿼리가 많아서(확대 평가셋 기준 47%),
# 재랭킹이 아무리 잘해도 한계가 있다. 키워드 검색(BM25) 후보를 함께 모아 한 풀로 만든 뒤
# LLM이 재랭킹하게 한다 (backend/evaluation/bench 의 실험 참고).
_keyword_index = None


def _bigrams(text: str) -> list[str]:
    """한글은 띄어쓰기 단위로 자르면 조사 때문에 잘 안 맞아서 2글자 조각으로 비교한다."""
    t = re.sub(r"[^0-9A-Za-z가-힣]", "", text.lower())
    return [t[i : i + 2] for i in range(len(t) - 1)] or [t]


def _get_keyword_index():
    global _keyword_index
    if _keyword_index is None:
        data = _get_collection().get(include=["documents"])
        ids, docs = data["ids"], data["documents"]
        tf = [Counter(_bigrams(d)) for d in docs]
        lengths = [sum(c.values()) for c in tf]
        df: Counter = Counter()
        for c in tf:
            df.update(c.keys())
        _keyword_index = (ids, tf, lengths, sum(lengths) / max(len(lengths), 1), df)
    return _keyword_index


def keyword_search(query: str, n_results: int = 10) -> list[str]:
    """레시피 설명(embedding_text)에 대한 BM25 키워드 검색. 점수가 같으면 색인 순서."""
    ids, tf, lengths, avg_len, df = _get_keyword_index()
    n = len(ids)
    scored = []
    for i in range(n):
        score = 0.0
        for term in set(_bigrams(query)):
            freq = tf[i].get(term, 0)
            if not freq:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * freq * 2.5 / (freq + 1.5 * (0.25 + 0.75 * lengths[i] / avg_len))
        if score > 0:
            scored.append((score, i))
    scored.sort(key=lambda x: -x[0])
    return [ids[i] for _, i in scored[:n_results]]


def search_pooled(query: str, n_vector: int = 10, n_keyword: int = 10, max_candidates: int = 20) -> list[str]:
    """벡터(+카테고리 필터) 후보와 키워드 후보를 번갈아 담아 하나의 후보 풀로 합친다 (중복 제거).

    한쪽 검색이 앞에 몰리지 않게 번갈아 담는다. 재랭킹은 이 풀을 받아 순서를 다시 매긴다.
    """
    vector_refs = search(query, n_results=n_vector)
    keyword_refs = keyword_search(query, n_results=n_keyword)
    pooled: list[str] = []
    for i in range(max(len(vector_refs), len(keyword_refs))):
        for refs in (vector_refs, keyword_refs):
            if i < len(refs) and refs[i] not in pooled:
                pooled.append(refs[i])
    return pooled[:max_candidates]
