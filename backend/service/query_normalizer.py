from openai import OpenAI
from config import settings

client = OpenAI(api_key=settings.openai_api_key)

NORMALIZE_SYSTEM_PROMPT = (
    "너는 사용자의 자연어 음식 요청을 레시피 검색에 쓰기 좋은 짧은 검색어로 정리하는 역할이야.\n\n"
    "규칙:\n"
    "- 반드시 '음식 형태(면/국물/밥/구이/볶음/샐러드 등), 맛·특징(매콤함/담백함/새콤함/든든함 등), "
    "재료, 상황(혼밥/간단함/해장 등)' 순서로, 쉼표로 구분해서 나열해. 음식 형태를 항상 제일 앞에 써.\n"
    "- '얼큰한 국물'처럼 맛 표현을 명사 앞에 수식어로 붙이지 말고, '국물, 얼큰함'처럼 명사와 맛 표현을 "
    "분리해서 써.\n"
    "- 말투·감탄사·조사는 다 빼고, 완전한 문장으로 쓰지 마.\n"
    "- 사용자가 말하지 않은 내용을 추측해서 새로 추가하지 마.\n"
    "- 설명, 따옴표, 다른 말 없이 정리된 검색어만 출력해."
)


def normalize_query(query: str) -> str:
    """자유 형식 자연어 요청을 임베딩 검색에 쓸 짧은 검색어로 정리한다.

    같은 의미라도 문장에서 핵심 수식어가 앞/뒤 어디에 오는지에 따라 임베딩 유사도
    검색 결과가 크게 흔들리는 걸 확인해서(예: "얼큰한 국물 요리가 떙기네"는 국물
    요리가 아닌 반찬이 1위로 나왔는데, 같은 뜻을 "국물 요리, 얼큰함"처럼 정리하면
    정상적으로 국물찌개류가 상위에 옴), 임베딩 직전에 LLM으로 한 번 정규화한다.
    실패하면 원본 쿼리를 그대로 써서 검색 자체는 계속 동작하게 한다.
    """
    try:
        completion = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": NORMALIZE_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
        )
        normalized = (completion.choices[0].message.content or "").strip()
        return normalized or query
    except Exception:
        return query
