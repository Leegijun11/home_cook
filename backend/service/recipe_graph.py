import json
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
    "- [필수 분량]이 주어졌다면 그 수치가 steps 문장 안에 정확히 반영됐는가 (빠졌거나 뭉뚱그렸으면 감점)\n"
    "- 재료 목록과 조리 순서가 서로 모순되지 않는가\n\n"
    "반드시 아래 JSON 형식으로만 응답해. 다른 설명은 포함하지 마.\n"
    '{"score": 0에서 10 사이 숫자, "issues": ["문제점", ...], "suggestions": ["개선 제안", ...]}\n'
    "문제가 없으면 issues는 빈 배열로 둬."
)


class RecipeState(TypedDict):
    recipe: dict
    spice_level: Optional[str]
    doneness: Optional[str]
    generated_recipe: dict
    critic_feedback: dict
    retry_done: bool


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
    return {"generated_recipe": generated}


def critique_node(state: RecipeState):
    generated = state["generated_recipe"]
    prompt = "\n".join([
        f"메뉴: {generated.get('menu')}",
        f"재료: {', '.join(generated.get('ingredients') or [])}",
        "",
        "조리 순서:",
        generated.get("steps") or "",
        "",
        _required_amounts_text(state["recipe"], state["spice_level"], state["doneness"]),
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
    return {"generated_recipe": generated, "retry_done": True}


def should_retry(state: RecipeState):
    feedback = state["critic_feedback"]
    if feedback.get("score", 10) < settings.critic_score_threshold and not state["retry_done"]:
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
        "retry_done": False,
    }
    final_state = recipe_graph.invoke(initial_state)
    return final_state["generated_recipe"], final_state["critic_feedback"]
