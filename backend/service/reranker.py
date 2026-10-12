import json

from openai import OpenAI

from config import settings

client = OpenAI(api_key=settings.openai_api_key)

RERANK_SYSTEM_PROMPT = (
    "너는 사용자의 자연어 음식 요청에 맞게 레시피 후보 목록의 순서를 다시 매기는 역할이야.\n\n"
    "사용자 요청과 레시피 후보 목록(번호, 메뉴명, 설명)이 주어져. 각 레시피 설명을 실제로 읽고, "
    "사용자가 원하는 맛·식감·상황에 가장 잘 맞는 순서대로 번호를 나열해줘.\n\n"
    "규칙:\n"
    "- 설명에 실제로 드러난 맛·재료·조리법만 근거로 판단해. 설명에 없는 내용을 추측하지 마.\n"
    "- 후보 목록에 있는 번호를 빠짐없이, 중복 없이 전부 포함해.\n"
    "- 반드시 아래 JSON 형식으로만 응답해. 다른 설명은 포함하지 마.\n"
    '{"ranked_ids": [번호, 번호, ...]}'
)


def rerank(query: str, candidates: list[dict]) -> list[dict]:
    """임베딩 검색(+카테고리 필터)으로 뽑은 후보들을 LLM이 실제 설명을 읽고 다시 정렬한다.

    벡터 유사도는 토픽만 비슷해도 높게 나오는 경우가 많다(예: "매콤한 밥" 쿼리에
    안 매운 볶음밥이 올라오는 것). 후보 수가 10개 수준으로 적을 때는 LLM이 각
    설명을 직접 읽고 판단하는 게 더 정확하다. 실패하면 원래 순서를 그대로
    반환해서 검색 자체는 계속 동작하게 한다.
    """
    if len(candidates) <= 1:
        return candidates

    numbered = "\n".join(
        f"{i}. {c.get('name')} - {c.get('embedding_text') or ''}"
        for i, c in enumerate(candidates, start=1)
    )
    prompt = f"사용자 요청: {query}\n\n레시피 후보:\n{numbered}"

    try:
        completion = client.chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": RERANK_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        order = json.loads(completion.choices[0].message.content).get("ranked_ids") or []

        reranked = [candidates[i - 1] for i in order if isinstance(i, int) and 1 <= i <= len(candidates)]
        seen = {id(c) for c in reranked}
        reranked += [c for c in candidates if id(c) not in seen]  # 누락/중복 보정
        return reranked
    except Exception:
        return candidates
