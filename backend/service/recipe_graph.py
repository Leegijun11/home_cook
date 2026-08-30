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
    "- '기본 조리방법'은 재료와 순서의 큰 흐름만 참고하고 그대로 베끼지 마. 실제 steps는 네가 아는 "
    "일반적인 조리 지식을 활용해서 훨씬 더 구체적으로 새로 써. 불 세기(센 불/중불/약불), 대략적인 "
    "조리 시간, 재료 상태 변화(예: 양파가 투명해질 때까지, 표면이 노릇해질 때까지, 국물이 자작해질 "
    "때까지)를 최소 두 군데 이상 포함해.\n"
    "- [필수 재료](맵기 단계별로 들어가는 재료)는 steps 안에 반드시 이름이 등장해야 해. 정확한 분량까지 "
    "적을 필요는 없어 — '고춧가루를 넣어 매운맛을 낸다'처럼 자연스럽게 언급만 하면 충분해.\n"
    "- [필수 분량](굽기 단계별 시간/온도)은 절대 임의로 바꾸거나 뭉뚱그리지 마. steps 문장 안에 그 "
    "수치를 그대로 적어.\n"
    "- [대체 재료]가 주어지면 그건 다른 규칙보다 우선이야. 원래 재료 이름은 ingredients와 steps 어디에도 "
    "단 한 글자도 남기지 말고, 전부 대체 재료 이름으로 바꿔서 써.\n"
    "- steps는 처음부터 끝까지 자연스럽게 이어지는 하나의 조리 순서여야 해. 같은 내용이나 비슷한 문장을 "
    "두 번 반복해서 쓰지 마.\n"
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
    substitutions: dict[str, str]
    generated_recipe: dict
    critic_feedback: dict
    missing_ingredients: list[str]
    missing_amounts: list[str]
    substitution_issues: list[str]
    retry_done: bool


def _spice_overrides(recipe: dict, spice_level: Optional[str]):
    if not spice_level:
        return {}
    return (recipe.get("spice_level_table") or {}).get(spice_level, {})


def _doneness_overrides(recipe: dict, doneness: Optional[str]):
    if not doneness:
        return {}
    return (recipe.get("doneness_table") or {}).get(doneness, {})


def _required_amounts_text(recipe: dict, spice_level: Optional[str], doneness: Optional[str]):
    lines = []

    spice_overrides = _spice_overrides(recipe, spice_level)
    if spice_overrides:
        override_text = ", ".join(f"{name} {amount}" for name, amount in spice_overrides.items())
        lines += [f"선택한 맵기 단계: {spice_level}", f"[필수 재료] {override_text}"]

    doneness_overrides = _doneness_overrides(recipe, doneness)
    if doneness_overrides:
        override_text = ", ".join(f"{name} {amount}" for name, amount in doneness_overrides.items())
        lines += [f"선택한 굽기 단계: {doneness}", f"[필수 분량] {override_text}"]

    return "\n".join(lines)


def _substitutions_text(substitutions: dict):
    if not substitutions:
        return ""
    lines = [f"{original} 대신 {replacement} 사용" for original, replacement in substitutions.items()]
    return "[대체 재료] (원래 재료 대신 반드시 이걸 사용):\n" + "\n".join(lines)


def _amount_tokens(amount: str):
    """분량 문자열에서 숫자가 포함된 조각만 뽑아낸다.

    예: "한 면당 4분 이상" -> ["4분"], "60~63도" -> ["60~63도"]. 요리사 에이전트가
    "한 면당"처럼 곁말은 바꿔 쓰더라도 실제 숫자(분/도/큰술 등)만 있으면 충분하다고 본다.
    """
    tokens = re.findall(r"\d+[^\s,]*", amount)
    return tokens or [amount]


def _missing_required_ingredients(recipe: dict, spice_level: Optional[str], steps: Optional[str]):
    """맵기 단계의 [필수 재료] 이름이 steps에 언급됐는지만 확인 (정확한 분량은 요구하지 않음).

    스터디용 프로젝트라 "고춧가루 2.5큰술"처럼 토씨까지 맞추는 건 과한 엄격함이라 판단해서,
    이 항목은 재료 이름이 등장하는지만 결정론적으로 확인한다.
    """
    overrides = _spice_overrides(recipe, spice_level)
    steps = steps or ""
    return [name for name, amount in overrides.items() if amount != "0" and name not in steps]


def _missing_required_amounts(recipe: dict, doneness: Optional[str], steps: Optional[str]):
    """굽기 단계의 [필수 분량] 숫자가 steps 문장 안에 실제로 들어있는지 코드로 직접 검사.

    시간/온도는 재료 언급과 달리 실제 조리 결과에 영향을 주는 정보라 계속 정확하게 확인한다.
    미식가 LLM이 이 판단을 자주 헛짚어서(있는데 없다고 하거나 반대로) 여기만 떼어내
    문자열 포함 여부로 결정론적으로 확인한다.
    """
    overrides = _doneness_overrides(recipe, doneness)
    steps = steps or ""
    missing = []
    for name, amount in overrides.items():
        if not all(token in steps for token in _amount_tokens(amount)):
            missing.append(f"{name} {amount}")
    return missing


def _substitution_violations(substitutions: dict, generated: dict):
    """[대체 재료] 지침이 실제로 지켜졌는지 코드로 직접 검사.

    원본 재료 이름이 아직 남아있거나 대체 재료 이름이 전혀 안 보이면 위반으로 본다.
    """
    text = " ".join(generated.get("ingredients") or []) + " " + (generated.get("steps") or "")
    violations = []
    for original, replacement in substitutions.items():
        if original in text or replacement not in text:
            violations.append(f"{original} → {replacement}")
    return violations


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
        _substitutions_text(state.get("substitutions") or {}),
        "",
        _required_amounts_text(recipe, state["spice_level"], state["doneness"]),
    ])
    generated = _call_llm(COOK_SYSTEM_PROMPT, prompt)
    missing_ingredients = _missing_required_ingredients(recipe, state["spice_level"], generated.get("steps"))
    missing_amounts = _missing_required_amounts(recipe, state["doneness"], generated.get("steps"))
    sub_issues = _substitution_violations(state.get("substitutions") or {}, generated)
    return {
        "generated_recipe": generated,
        "missing_ingredients": missing_ingredients,
        "missing_amounts": missing_amounts,
        "substitution_issues": sub_issues,
    }


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
    """생성을 처음부터 다시 한다 (이전 결과물은 프롬프트에 넣지 않음).

    이전 결과 JSON을 그대로 보여주고 "수정해"라고 시켰더니 GPT가 새로 쓰는 대신 비슷한
    문장을 이어붙이는 경우가 있어서, 대신 "이번엔 이런 실수를 하지 마"라는 주의사항만
    추가로 얹어 generate_node와 동일하게 완전히 새로 작성하게 한다.
    """
    recipe = state["recipe"]

    mistakes = []
    if state.get("missing_ingredients"):
        mistakes.append(f"필수 재료가 문장에서 언급 안 됨: {', '.join(state['missing_ingredients'])}")
    if state.get("missing_amounts"):
        mistakes.append(f"필수 분량이 문장에서 빠짐: {', '.join(state['missing_amounts'])}")
    if state.get("substitution_issues"):
        mistakes.append(f"대체 재료가 제대로 안 바뀜: {', '.join(state['substitution_issues'])}")
    for issue in (state["critic_feedback"].get("issues") or []):
        mistakes.append(issue)

    prompt = "\n".join([
        f"메뉴: {recipe.get('name')}",
        f"기본 재료: {', '.join(recipe.get('base_ingredients') or [])}",
        f"주 조리도구: {recipe.get('main_tool')}",
        "",
        "기본 조리방법:",
        recipe.get("steps") or "",
        "",
        _substitutions_text(state.get("substitutions") or {}),
        "",
        _required_amounts_text(recipe, state["spice_level"], state["doneness"]),
        "",
        "[주의] 이전 시도에서 아래 실수가 있었어. 처음부터 새로 하나의 매끄러운 레시피를 "
        "작성하면서 이 실수를 반드시 피해:",
        "\n".join(f"- {mistake}" for mistake in mistakes),
    ])
    generated = _call_llm(COOK_SYSTEM_PROMPT, prompt)
    missing_ingredients = _missing_required_ingredients(recipe, state["spice_level"], generated.get("steps"))
    missing_amounts = _missing_required_amounts(recipe, state["doneness"], generated.get("steps"))
    sub_issues = _substitution_violations(state.get("substitutions") or {}, generated)
    return {
        "generated_recipe": generated,
        "missing_ingredients": missing_ingredients,
        "missing_amounts": missing_amounts,
        "substitution_issues": sub_issues,
        "retry_done": True,
    }


def should_retry(state: RecipeState):
    feedback = state["critic_feedback"]
    score_too_low = feedback.get("score", 10) < settings.critic_score_threshold
    has_missing_ingredients = bool(state.get("missing_ingredients"))
    has_missing_amounts = bool(state.get("missing_amounts"))
    has_substitution_issues = bool(state.get("substitution_issues"))
    if not state["retry_done"] and (
        score_too_low or has_missing_ingredients or has_missing_amounts or has_substitution_issues
    ):
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


def run(recipe: dict, spice_level: Optional[str], doneness: Optional[str], substitutions: Optional[dict] = None):
    initial_state: RecipeState = {
        "recipe": recipe,
        "spice_level": spice_level,
        "doneness": doneness,
        "substitutions": substitutions or {},
        "generated_recipe": {},
        "critic_feedback": {},
        "missing_ingredients": [],
        "missing_amounts": [],
        "substitution_issues": [],
        "retry_done": False,
    }
    final_state = recipe_graph.invoke(initial_state)

    feedback = dict(final_state["critic_feedback"])
    issues = list(feedback.get("issues") or [])

    sub_issues = final_state.get("substitution_issues") or []
    if sub_issues:
        issues = [f"대체 재료 미반영: {', '.join(sub_issues)}"] + issues

    missing_amounts = final_state.get("missing_amounts") or []
    if missing_amounts:
        issues = [f"필수 분량 누락: {', '.join(missing_amounts)}"] + issues

    missing_ingredients = final_state.get("missing_ingredients") or []
    if missing_ingredients:
        issues = [f"필수 재료 언급 안 됨: {', '.join(missing_ingredients)}"] + issues

    feedback["issues"] = issues
    return final_state["generated_recipe"], feedback
