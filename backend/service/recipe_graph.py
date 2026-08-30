import json
import re
from typing import TypedDict, Optional
from openai import OpenAI
from langgraph.graph import StateGraph, END
from config import settings

client = OpenAI(api_key=settings.openai_api_key)

COOK_SYSTEM_PROMPT = (
    "너는 자취생을 위한 요리사 에이전트야. 주어진 기본 레시피에 사용자가 고른 맵기/굽기 단계를 반영해서 "
    "최종 레시피를 작성해.\n\n"
    "규칙:\n"
    "- [필수 분량]으로 표시된 재료와 수치는 절대 임의로 바꾸거나 뭉뚱그리지 마. steps 문장 안에서 그 "
    "재료가 등장하는 자리에 반드시 '재료명 + 수치'를 그대로 적어. ingredients 배열에만 적고 steps "
    "문장에는 수치를 빼는 것은 금지야.\n"
    '- 금지 표현 예시: "매운맛을 낸다", "매콤하게 볶는다", "고춧가루를 넣어 마무리한다" (수치 없음)\n'
    '- 올바른 예시: "고추장 2큰술과 고춧가루 1큰술을 넣어 매운맛을 낸다"\n'
    "- [필수 분량]이 없는 재료는 기본 레시피의 표현을 그대로 유지해도 돼.\n"
    "- 반드시 아래 JSON 형식으로만 응답해. 다른 설명, 마크다운, 코드블록은 포함하지 마.\n"
    '{"menu": "메뉴명", "ingredients": ["재료명 또는 재료명+분량", ...], "steps": "조리 순서 설명"}'
)

CRITIC_SYSTEM_PROMPT = (
    "너는 레시피를 평가하는 깐깐한 미식가 에이전트야. 자취생이 이 레시피만 보고 실제로 따라 만들 수 "
    "있을지 평가해.\n\n"
    "평가 기준:\n"
    "- 조리 순서가 구체적이고 따라 하기 쉬운가\n"
    "- 재료 목록과 조리 순서가 서로 모순되지 않는가\n"
    "- 전체적으로 맛있게 완성될 것 같은가\n\n"
    "참고: 맵기/굽기 단계별 필수 분량이 정확히 반영됐는지는 이미 코드로 별도 검증하니 너는 신경 쓰지 "
    "않아도 돼.\n\n"
    "반드시 아래 JSON 형식으로만 응답해. 다른 설명은 포함하지 마.\n"
    '{"score": 0에서 10 사이 숫자, "comment": "점수를 준 이유를 한두 문장으로", '
    '"issues": ["문제점", ...], "suggestions": ["개선 제안", ...]}\n'
    "comment는 점수가 높든 낮든 항상 채워. issues/suggestions는 문제나 개선점이 없으면 빈 배열로 둬."
)


class RecipeState(TypedDict):
    recipe: dict
    spice_level: Optional[str]
    doneness: Optional[str]
    generated_recipe: dict
    critic_feedback: dict
    missing_amounts: list[str]
    retry_done: bool


def _required_overrides(recipe: dict, spice_level: Optional[str], doneness: Optional[str]):
    overrides = {}
    if spice_level:
        overrides.update((recipe.get("spice_level_table") or {}).get(spice_level, {}))
    if doneness:
        overrides.update((recipe.get("doneness_table") or {}).get(doneness, {}))
    return overrides


def _required_amounts_text(recipe: dict, spice_level: Optional[str], doneness: Optional[str]):
    lines = []

    if spice_level:
        overrides = (recipe.get("spice_level_table") or {}).get(spice_level, {})
        override_text = ", ".join(f"{name} {amount}" for name, amount in overrides.items())
        lines += [f"선택한 맵기 단계: {spice_level}", f"[필수 분량] {override_text}"]

    if doneness:
        overrides = (recipe.get("doneness_table") or {}).get(doneness, {})
        override_text = ", ".join(f"{name} {amount}" for name, amount in overrides.items())
        lines += [f"선택한 굽기 단계: {doneness}", f"[필수 분량] {override_text}"]

    return "\n".join(lines)


def _amount_tokens(amount: str):
    """분량 문자열에서 숫자가 포함된 조각만 뽑아낸다.

    예: "한 면당 4분 이상" -> ["4분"], "60~63도" -> ["60~63도"]. 요리사 에이전트가
    "한 면당"처럼 곁말은 바꿔 쓰더라도 실제 숫자(분/도/큰술 등)만 있으면 충분하다고 본다.
    """
    tokens = re.findall(r"\d+[^\s,]*", amount)
    return tokens or [amount]


def _missing_required_amounts(recipe: dict, spice_level: Optional[str], doneness: Optional[str], steps: Optional[str]):
    """[필수 분량]의 숫자가 steps 문장 안에 실제로 들어있는지 코드로 직접 검사.

    미식가 LLM이 이 판단을 자주 헛짚어서(있는데 없다고 하거나 반대로) 여기만 떼어내
    문자열 포함 여부로 결정론적으로 확인한다.
    """
    overrides = _required_overrides(recipe, spice_level, doneness)
    steps = steps or ""
    missing = []
    for name, amount in overrides.items():
        if not all(token in steps for token in _amount_tokens(amount)):
            missing.append(f"{name} {amount}")
    return missing


def _call_llm(system_prompt: str, user_prompt: str):
    completion = client.chat.completions.create(
        model=settings.openai_model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return json.loads(completion.choices[0].message.content)


def generate_node(state: RecipeState):
    recipe = state["recipe"]
    prompt = "\n".join([
        f"메뉴: {recipe.get('name')}",
        f"기본 재료: {', '.join(recipe.get('base_ingredients') or [])}",
        f"주 조리도구: {recipe.get('main_tool')}",
        "",
        "기본 조리방법:",
        recipe.get("steps") or "",
        "",
        _required_amounts_text(recipe, state["spice_level"], state["doneness"]),
    ])
    generated = _call_llm(COOK_SYSTEM_PROMPT, prompt)
    missing = _missing_required_amounts(recipe, state["spice_level"], state["doneness"], generated.get("steps"))
    return {"generated_recipe": generated, "missing_amounts": missing}


def critique_node(state: RecipeState):
    generated = state["generated_recipe"]
    prompt = "\n".join([
        f"메뉴: {generated.get('menu')}",
        f"재료: {', '.join(generated.get('ingredients') or [])}",
        "",
        "조리 순서:",
        generated.get("steps") or "",
    ])
    feedback = _call_llm(CRITIC_SYSTEM_PROMPT, prompt)
    return {"critic_feedback": feedback}


def regenerate_node(state: RecipeState):
    recipe = state["recipe"]
    generated = state["generated_recipe"]
    feedback = state["critic_feedback"]
    prompt = "\n".join([
        f"메뉴: {recipe.get('name')}",
        f"기본 재료: {', '.join(recipe.get('base_ingredients') or [])}",
        f"주 조리도구: {recipe.get('main_tool')}",
        "",
        _required_amounts_text(recipe, state["spice_level"], state["doneness"]),
        "",
        "이전에 생성한 레시피:",
        json.dumps(generated, ensure_ascii=False),
        "",
        "미식가 피드백 (반드시 반영해서 수정할 것):",
        f"문제점: {', '.join(feedback.get('issues') or [])}",
        f"개선 제안: {', '.join(feedback.get('suggestions') or [])}",
    ])
    generated = _call_llm(COOK_SYSTEM_PROMPT, prompt)
    missing = _missing_required_amounts(recipe, state["spice_level"], state["doneness"], generated.get("steps"))
    return {"generated_recipe": generated, "missing_amounts": missing, "retry_done": True}


def should_retry(state: RecipeState):
    feedback = state["critic_feedback"]
    score_too_low = feedback.get("score", 10) < settings.critic_score_threshold
    has_missing_amounts = bool(state.get("missing_amounts"))
    if not state["retry_done"] and (score_too_low or has_missing_amounts):
        return "retry"
    return "done"


def _build_graph():
    graph = StateGraph(RecipeState)
    graph.add_node("generate", generate_node)
    graph.add_node("critique", critique_node)
    graph.add_node("regenerate", regenerate_node)
    graph.set_entry_point("generate")
    graph.add_edge("generate", "critique")
    graph.add_conditional_edges("critique", should_retry, {"retry": "regenerate", "done": END})
    graph.add_edge("regenerate", END)
    return graph.compile()


recipe_graph = _build_graph()


def run(recipe: dict, spice_level: Optional[str], doneness: Optional[str]):
    initial_state: RecipeState = {
        "recipe": recipe,
        "spice_level": spice_level,
        "doneness": doneness,
        "generated_recipe": {},
        "critic_feedback": {},
        "missing_amounts": [],
        "retry_done": False,
    }
    final_state = recipe_graph.invoke(initial_state)

    feedback = dict(final_state["critic_feedback"])
    missing = final_state.get("missing_amounts") or []
    if missing:
        feedback["issues"] = [f"필수 분량 누락: {', '.join(missing)}"] + list(feedback.get("issues") or [])

    return final_state["generated_recipe"], feedback
