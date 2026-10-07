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


def search(query: str, n_results: int = 10) -> list[str]:
    """자연어 쿼리와 의미적으로 가까운 레시피를 유사도순 recipe_ref 리스트로 반환."""
    collection = _get_collection()
    if collection.count() == 0:
        return []

    vector = _embed([query])[0]
    result = collection.query(query_embeddings=[vector], n_results=n_results)
    ids = result.get("ids") or []
    return ids[0] if ids else []
