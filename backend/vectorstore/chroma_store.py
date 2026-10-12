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
