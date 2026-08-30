import json
from sqlalchemy.orm import Session
from openai import OpenAI
from crud.category import CategoryCrud
from crud.ingredients import IngredientCrud
from crud.recipe import RecipeCrud
from schema.recipe import GenerateRequest
from config import settings
from fastapi import HTTPException

client = OpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = (
    "너는 자취생을 위한 요리사 에이전트야. 주어진 기본 레시피와 사용자가 고른 맵기/굽기 단계를 "
    "반영해서 최종 레시피를 작성해. 반드시 아래 JSON 형식으로만 응답해:\n"
    '{"menu": "메뉴명", "ingredients": ["재료1", "재료2"], "steps": "조리 순서 설명"}'
)


class RecipeService:

    @staticmethod
    def get_candidate(category_id: int, db: Session):
        category = CategoryCrud.get_category(category_id, db)
        if category is None:
            raise HTTPException(status_code=404, detail="Error: 선택된 카테고리를 찾을 수 없음")

        owned_names = {ingredient.name for ingredient in IngredientCrud.get_owned_ingredients(db)}
        candidates = RecipeCrud.find_matching_recipes(category.cuisine, category.dish_type)

        for recipe in candidates:
            base_ingredients = set(recipe.get("base_ingredients") or [])
            if base_ingredients <= owned_names:
                spice_level_table = recipe.get("spice_level_table")
                doneness_table = recipe.get("doneness_table")

                return {
                    "status": "ready",
                    "recipe_ref": recipe["recipe_ref"],
                    "menu": recipe.get("name"),
                    "needs_spice": spice_level_table is not None,
                    "needs_doneness": doneness_table is not None,
                    "spice_options": list(spice_level_table.keys()) if spice_level_table else [],
                    "doneness_options": list(doneness_table.keys()) if doneness_table else [],
                }

        return {"status": "no_candidate"}

    @staticmethod
    def _build_prompt(recipe: dict, spice_level: str | None, doneness: str | None):
        lines = [
            f"메뉴: {recipe.get('name')}",
            f"기본 재료: {', '.join(recipe.get('base_ingredients') or [])}",
            f"주 조리도구: {recipe.get('main_tool')}",
            "",
            "기본 조리방법:",
            recipe.get("steps") or "",
        ]

        if spice_level:
            overrides = (recipe.get("spice_level_table") or {}).get(spice_level, {})
            lines += ["", f"선택한 맵기 단계: {spice_level}", f"맵기 단계별 재료량 조정: {overrides}"]

        if doneness:
            overrides = (recipe.get("doneness_table") or {}).get(doneness, {})
            lines += ["", f"선택한 굽기 단계: {doneness}", f"굽기 단계별 조정: {overrides}"]

        return "\n".join(lines)

    @staticmethod
    def generate(payload: GenerateRequest):
        recipe = RecipeCrud.get_by_ref(payload.recipe_ref)
        if recipe is None:
            raise HTTPException(status_code=404, detail="Error: 확정된 레시피를 찾을 수 없음")

        spice_level_table = recipe.get("spice_level_table")
        if payload.spice_level and (not spice_level_table or payload.spice_level not in spice_level_table):
            raise HTTPException(status_code=400, detail="Error: 유효하지 않은 맵기 단계")

        doneness_table = recipe.get("doneness_table")
        if payload.doneness and (not doneness_table or payload.doneness not in doneness_table):
            raise HTTPException(status_code=400, detail="Error: 유효하지 않은 굽기 단계")

        prompt = RecipeService._build_prompt(recipe, payload.spice_level, payload.doneness)

        try:
            completion = client.chat.completions.create(
                model=settings.openai_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail="Error: 레시피 생성 요청이 실패함") from e

        try:
            parsed = json.loads(completion.choices[0].message.content)
            return {
                "status": "done",
                "menu": parsed["menu"],
                "ingredients": parsed["ingredients"],
                "steps": parsed["steps"],
            }
        except (KeyError, ValueError) as e:
            raise HTTPException(status_code=502, detail="Error: 레시피 생성 결과를 해석하지 못함") from e
