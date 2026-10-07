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

    매번 전체 삭제 후 새로 넣는다 — 레시피 수가 수백 개 수준이라 증분 업데이트보다
    단순하고, recipe_ref가 바뀌거나 삭제된 레시피가 남아있는 문제도 피할 수 있다.
    """
    collection = _get_collection()
    existing_ids = collection.get()["ids"]
    if existing_ids:
        collection.delete(ids=existing_ids)

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
