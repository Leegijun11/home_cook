"""home_cook 검색 평가용 공용 모듈.

DB(MySQL)와 ChromaDB 없이 같은 순위가 나오도록 재현한다.
- 벡터 검색: OpenAI 임베딩은 길이가 1로 정규화돼 있어서 코사인 유사도 순위 = Chroma 기본(L2) 순위와 같다.
- 카테고리 필터: backend/vectorstore/chroma_store.py 의 규칙을 그대로 옮겼다.
- 재랭킹 프롬프트: backend/service/reranker.py 와 같은 문구.
모든 API 호출은 토큰 사용량을 ledger.jsonl 에 기록한다 (비용 추정용).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import threading
import time
from collections import Counter
from pathlib import Path

import numpy as np
from dotenv import dotenv_values
from openai import OpenAI

HERE = Path(__file__).resolve().parent
BACKEND_DIR = HERE.parents[1]
CACHE_DIR = HERE / "cache"
CACHE_DIR.mkdir(exist_ok=True)
LEDGER = CACHE_DIR / "ledger.jsonl"
ENV_FILE = BACKEND_DIR / ".env"  # 서비스와 같은 backend/.env 의 OPENAI_API_KEY 를 쓴다

EMBEDDING_MODEL = "text-embedding-3-large"  # home_cook/backend/config.py 와 같음
DEFAULT_LLM = os.environ.get("HC_MODEL", "gpt-5-mini")  # home_cook 의 기본 모델

_lock = threading.Lock()
_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        key = dotenv_values(ENV_FILE).get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY 를 찾지 못했습니다")
        _client = OpenAI(api_key=key, max_retries=4, timeout=180)
    return _client


def _log(kind: str, model: str, usage) -> None:
    row = {"t": time.time(), "kind": kind, "model": model}
    if usage is not None:
        row["prompt"] = getattr(usage, "prompt_tokens", None)
        row["completion"] = getattr(usage, "completion_tokens", None)
        details = getattr(usage, "completion_tokens_details", None)
        row["reasoning"] = getattr(details, "reasoning_tokens", None) if details else None
        row["total"] = getattr(usage, "total_tokens", None)
    with _lock, LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def ledger_summary() -> dict:
    out: dict = {}
    if not LEDGER.exists():
        return out
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        key = f"{r['kind']}:{r['model']}"
        s = out.setdefault(key, {"calls": 0, "prompt": 0, "completion": 0, "reasoning": 0})
        s["calls"] += 1
        s["prompt"] += r.get("prompt") or 0
        s["completion"] += r.get("completion") or 0
        s["reasoning"] += r.get("reasoning") or 0
    return out


# ---------------------------------------------------------------- 임베딩 (디스크 캐시)
def _embed_cache_path(text: str) -> Path:
    h = hashlib.sha1((EMBEDDING_MODEL + "\n" + text).encode("utf-8")).hexdigest()
    return CACHE_DIR / "emb" / f"{h}.npy"


def embed(texts: list[str]) -> np.ndarray:
    (CACHE_DIR / "emb").mkdir(exist_ok=True)
    vectors: list[np.ndarray | None] = [None] * len(texts)
    todo = []
    for i, t in enumerate(texts):
        p = _embed_cache_path(t)
        if p.exists():
            vectors[i] = np.load(p)
        else:
            todo.append(i)
    for start in range(0, len(todo), 100):
        chunk = todo[start : start + 100]
        resp = client().embeddings.create(model=EMBEDDING_MODEL, input=[texts[i] for i in chunk])
        _log("embedding", EMBEDDING_MODEL, resp.usage)
        for i, item in zip(chunk, resp.data):
            v = np.array(item.embedding, dtype=np.float32)
            np.save(_embed_cache_path(texts[i]), v)
            vectors[i] = v
    m = np.vstack(vectors)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


# ---------------------------------------------------------------- 카테고리 필터 (chroma_store.py 와 동일)
DISH_TYPE_KEYWORDS = {
    "국물/찌개류": ["국물", "찌개", "탕", "수프"],
    "면류": ["면", "국수", "파스타", "우동", "라멘"],
    "밥류": ["밥", "덮밥", "리조또"],
    "볶음류": ["볶음"],
    "구이류": ["구이", "꼬치", "스테이크"],
    "샐러드/간편식": ["샐러드", "무침", "반찬", "초밥", "간편식"],
}


def detect_dish_types(query: str) -> list[str]:
    return [dt for dt, kws in DISH_TYPE_KEYWORDS.items() if any(k in query for k in kws)]


# ---------------------------------------------------------------- 검색 인덱스
def _bigrams(text: str) -> list[str]:
    t = re.sub(r"[^0-9A-Za-z가-힣]", "", text.lower())
    return [t[i : i + 2] for i in range(len(t) - 1)] or [t]


class Index:
    def __init__(self, recipes: list[dict]):
        self.recipes = recipes
        self.refs = [r["recipe_ref"] for r in recipes]
        self.by_ref = {r["recipe_ref"]: r for r in recipes}
        self.matrix = embed([r["embedding_text"] for r in recipes])
        # BM25 (한글 2글자 조각 기반). 색인 문서 = 임베딩에 쓰는 텍스트와 같은 것
        docs = [_bigrams(r["embedding_text"]) for r in recipes]
        self.tf = [Counter(d) for d in docs]
        self.dl = [len(d) for d in docs]
        self.avgdl = sum(self.dl) / len(self.dl)
        self.df: Counter = Counter()
        for c in self.tf:
            self.df.update(c.keys())

    def vector_search(self, query: str, k: int = 10, use_filter: bool = True) -> list[str]:
        q = embed([query])[0]
        scores = self.matrix @ q
        allowed = None
        if use_filter:
            dts = detect_dish_types(query)
            if dts:
                allowed = {i for i, r in enumerate(self.recipes) if r["dish_type"] in dts}
        order = np.argsort(-scores)
        out = []
        for i in order:
            if allowed is not None and int(i) not in allowed:
                continue
            out.append(self.refs[int(i)])
            if len(out) == k:
                break
        return out

    def bm25_search(self, query: str, k: int = 10) -> list[str]:
        terms = set(_bigrams(query))
        n = len(self.recipes)
        scored = []
        for i in range(n):
            s = 0.0
            for t in terms:
                f = self.tf[i].get(t, 0)
                if not f:
                    continue
                idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                s += idf * f * 2.5 / (f + 1.5 * (0.25 + 0.75 * self.dl[i] / self.avgdl))
            if s > 0:
                scored.append((s, i))
        scored.sort(key=lambda x: -x[0])
        return [self.refs[i] for _, i in scored[:k]]


# ---------------------------------------------------------------- LLM 호출
RERANK_SYSTEM_PROMPT = (
    "너는 사용자의 자연어 음식 요청에 맞게 레시피 후보 목록의 순서를 다시 매기는 역할이야.\n\n"
    "사용자 요청과 레시피 후보 목록(번호, 메뉴명, 설명)이 주어져. 각 레시피 설명을 실제로 읽고, "
    "사용자가 원하는 맛·식감·상황에 가장 잘 맞는 순서대로 번호를 나열해줘.\n\n"
    "규칙:\n"
    "- 설명에 실제로 드러난 맛·재료·조리법만 근거로 판단해. 설명에 없는 내용을 추측하지 마.\n"
    "- 후보 목록에 있는 번호를 빠짐없이, 중복 없이 전부 포함해.\n"
    "- 반드시 아래 JSON 형식으로만 응답해. 다른 설명은 포함하지 마.\n"
    '{"ranked_ids": [번호, 번호, ...]}'
)  # backend/service/reranker.py 와 같은 문구

SCORE_SYSTEM_PROMPT = (
    "너는 사용자의 자연어 음식 요청과 레시피 후보 목록을 받아, 각 후보가 요청에 얼마나 맞는지 0~10점으로 매기는 역할이야.\n"
    "10점은 요청한 맛·식감·상황에 정확히 맞는 것, 0점은 전혀 아닌 것이야. "
    "설명에 실제로 드러난 맛·재료·조리법만 근거로 판단하고, 설명에 없는 내용을 추측하지 마. "
    "후보 번호마다 점수를 하나씩, 빠짐없이 매겨줘. 반드시 아래 JSON 형식으로만 응답해.\n"
    '{"scores": [{"id": 번호, "score": 0~10 정수}, ...]}'
)


def chat_json(system: str, user: str, model: str = DEFAULT_LLM, kind: str = "llm", **extra) -> dict:
    resp = client().chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        **extra,
    )
    _log(kind, model, resp.usage)
    return json.loads(resp.choices[0].message.content)


def _numbered(index: Index, refs: list[str]) -> str:
    return "\n".join(
        f"{i}. {index.by_ref[r]['name']} - {index.by_ref[r]['embedding_text']}"
        for i, r in enumerate(refs, start=1)
    )


def rerank_listwise(index: Index, query: str, refs: list[str], model: str = DEFAULT_LLM) -> list[str]:
    """home_cook 의 reranker.rerank 와 같은 방식 (번호를 순서대로 나열)."""
    if len(refs) <= 1:
        return refs
    prompt = f"사용자 요청: {query}\n\n레시피 후보:\n{_numbered(index, refs)}"
    try:
        order = chat_json(RERANK_SYSTEM_PROMPT, prompt, model, "rerank").get("ranked_ids") or []
    except Exception:
        return refs
    out = [refs[i - 1] for i in order if isinstance(i, int) and 1 <= i <= len(refs)]
    seen = set(out)
    return list(dict.fromkeys(out + [r for r in refs if r not in seen]))


def score_pointwise(
    index: Index, query: str, refs: list[str], model: str = DEFAULT_LLM, runs: int = 1, seed: int = 0
) -> list[str]:
    """후보마다 0~10점을 매기고 (여러 번이면 평균) 점수순으로 정렬. 동점은 원래 순서."""
    if len(refs) <= 1:
        return refs
    totals = {r: 0.0 for r in refs}
    for run in range(runs):
        order = list(refs)
        if run > 0:  # 매번 후보 순서를 섞어 위치 편향을 줄인다
            random.Random(f"{seed}:{query}:{run}").shuffle(order)
        prompt = f"사용자 요청: {query}\n\n레시피 후보:\n{_numbered(index, order)}"
        try:
            rows = chat_json(SCORE_SYSTEM_PROMPT, prompt, model, "score").get("scores") or []
        except Exception:
            rows = []
        for row in rows:
            i, s = row.get("id"), row.get("score")
            if isinstance(i, int) and 1 <= i <= len(order) and isinstance(s, (int, float)):
                totals[order[i - 1]] += float(s)
    position = {r: i for i, r in enumerate(refs)}
    return sorted(refs, key=lambda r: (-totals[r], position[r]))


# ---------------------------------------------------------------- 지표
def first_hit_rank(ranked: list[str], gold: set[str]) -> int | None:
    for i, r in enumerate(ranked, start=1):
        if r in gold:
            return i
    return None


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def summarize(ranks: list[int | None]) -> dict:
    n = len(ranks)
    out = {"n": n}
    for k in (1, 3, 5, 10):
        hits = sum(1 for r in ranks if r is not None and r <= k)
        lo, hi = wilson(hits, n)
        out[f"hit@{k}"] = (hits, round(hits / n, 3), round(lo, 3), round(hi, 3))
    out["mrr"] = round(sum((1 / r) if r else 0 for r in ranks) / n, 3)
    return out
