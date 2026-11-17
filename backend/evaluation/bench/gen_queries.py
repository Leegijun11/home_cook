"""레시피마다 자연어 검색 쿼리 2개를 만들어 평가셋(정답 = 그 레시피)을 만든다.

- 쿼리는 LLM 이 만들지만, 정답 레시피 이름·주재료가 그대로 들어간 쿼리는 코드가 걸러서 다시 만든다 (정답 누출 방지).
- 개발용/최종용은 쿼리가 아니라 '레시피' 단위로 나눈다 (같은 레시피의 두 쿼리가 양쪽에 섞이지 않게).
"""
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import core
from recipes import load_recipes

OUT = core.HERE / "queries.jsonl"
MODEL = core.DEFAULT_LLM

SYSTEM = (
    "너는 자취생이 요리 검색창에 입력할 문장을 만드는 역할이야. 레시피 하나를 받으면, 그 레시피를 찾고 싶은 사람이 "
    "메뉴 이름을 모른 채 입력할 법한 한국어 문장 2개를 만들어줘.\n\n"
    "규칙:\n"
    "- 첫 번째 문장은 맛·식감·온도 같은 느낌 중심, 두 번째 문장은 상황·기분·조리 조건 중심으로 써.\n"
    "- 두 문장 모두 레시피의 특징 하나 이상(조리법, 식감, 맛, 온도, 분위기 중)이 드러나야 해서, 아무 요리에나 맞는 일반적인 문장은 안 돼.\n"
    "- 메뉴 이름과 주재료 이름을 그대로 쓰지 마. 그 재료를 가리키는 다른 말도 피해.\n"
    "- 실제 사람이 말하듯 구어체로, 각 8~30자.\n"
    '- 반드시 아래 JSON 형식으로만 응답해: {"queries": ["첫 번째 문장", "두 번째 문장"]}'
)


def banned_words(recipe: dict) -> list[str]:
    words = [recipe["name"].replace(" ", "")]
    words += [i.replace(" ", "") for i in recipe["base_ingredients"] if len(str(i)) >= 2]
    return [w for w in dict.fromkeys(words) if w]


def violations(query: str, recipe: dict) -> list[str]:
    q = query.replace(" ", "")
    return [w for w in banned_words(recipe) if w in q]


def make_for(recipe: dict) -> list[str]:
    feedback = ""
    best: list[str] = []
    for attempt in range(4):
        user = (
            f"메뉴: {recipe['name']} ({recipe['cuisine']} {recipe['dish_type']})\n"
            f"설명: {recipe['embedding_text']}\n"
            f"주재료: {', '.join(map(str, recipe['base_ingredients']))}\n"
            f"조리방법:\n{recipe['body'][:700]}\n{feedback}"
        )
        try:
            qs = core.chat_json(SYSTEM, user, MODEL, "gen", reasoning_effort="minimal").get("queries") or []
        except Exception as e:  # 네트워크 오류 등은 다시 시도
            feedback = f"\n(이전 응답 오류: {type(e).__name__})"
            continue
        qs = [q.strip() for q in qs if isinstance(q, str) and 6 <= len(q.strip()) <= 60][:2]
        bad = {q: violations(q, recipe) for q in qs}
        if len(qs) == 2 and not any(bad.values()):
            return qs
        best = [q for q in qs if not bad[q]] or best
        bad_words = sorted({w for v in bad.values() for w in v})
        feedback = f"\n(주의: 이전 문장에 쓰면 안 되는 단어가 들어갔어: {', '.join(bad_words)}. 이 단어 없이 다시 써줘.)"
    return best  # 끝내 2개를 못 만들면 통과한 것만 쓴다


def split_of(ref: str) -> str:
    return "dev" if int(hashlib.sha1(ref.encode("utf-8")).hexdigest(), 16) % 10 < 4 else "test"


def main(limit: int | None = None) -> None:
    recipes = load_recipes()[:limit] if limit else load_recipes()
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(make_for, recipes))
    rows = []
    for r, qs in zip(recipes, results):
        for style, q in zip(("느낌", "상황"), qs):
            rows.append(
                {
                    "id": f"{len(rows):03d}",
                    "query": q,
                    "gold": r["recipe_ref"],
                    "style": style,
                    "split": split_of(r["recipe_ref"]),
                }
            )
    OUT.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    dev = sum(1 for x in rows if x["split"] == "dev")
    print(f"쿼리 {len(rows)}개 저장 (개발용 {dev}, 최종용 {len(rows) - dev}), 레시피 {len(recipes)}개")
    print("레시피별로 2개를 못 채운 경우:", sum(1 for qs in results if len(qs) < 2))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
