from sqlalchemy.orm import Session
from crud.category import CategoryCrud
from crud.ingredients import IngredientCrud
from crud.recipe import RecipeCrud
from schema.recipe import GenerateRequest
from service import recipe_graph
from fastapi import HTTPException


class RecipeService:

    @staticmethod
    def get_candidate(category_id: int, db: Session):
        category = CategoryCrud.get_category(category_id, db)
        if category is None:
            raise HTTPException(status_code=404, detail="Error: 선택된 카테고리를 찾을 수 없음")

        owned_names = {ingredient.name for ingredient in IngredientCrud.get_owned_ingredients(db)}
        candidates = RecipeCrud.find_matching_recipes(category.cuisine, category.dish_type)

        for recipe in candidates:
            if recipe.get("main_tool") not in owned_names:
                continue

            substitutions = RecipeService._resolve_substitutions(recipe, owned_names)
            if substitutions is None:
                continue

            spice_level_table = recipe.get("spice_level_table")
            doneness_table = recipe.get("doneness_table")
            spice_options = RecipeService._available_spice_levels(spice_level_table, owned_names)

            return {
                "status": "ready",
                "recipe_ref": recipe["recipe_ref"],
                "menu": recipe.get("name"),
                "needs_spice": len(spice_options) > 0,
                "needs_doneness": doneness_table is not None,
                "spice_options": spice_options,
                "doneness_options": list(doneness_table.keys()) if doneness_table else [],
                "substitutions": substitutions,
            }

        return {"status": "no_candidate"}

    @staticmethod
    def _resolve_substitutions(recipe: dict, owned_names: set):
        """base_ingredients 중 없는 것마다 substitution_table에서 보유한 대체재를 찾는다.

        하나라도 원본도 대체재도 없으면 이 레시피는 지금 재료로 불가능한 것이므로 None을 반환.
        """
        substitution_table = recipe.get("substitution_table") or {}
        substitutions = {}
        for ingredient in recipe.get("base_ingredients") or []:
            if ingredient in owned_names:
                continue
            alternatives = substitution_table.get(ingredient) or []
            replacement = next((alt for alt in alternatives if alt in owned_names), None)
            if replacement is None:
                return None
            substitutions[ingredient] = replacement
        return substitutions

    @staticmethod
    def _available_spice_levels(spice_level_table, owned_names: set):
        """맵기 단계 중, 그 단계에서 실제로 필요한 재료(양이 '0'이 아닌 것)를 전부
        보유하고 있는 단계만 골라서 반환. 하나도 없으면 빈 리스트(=맵기 선택 자체를 숨김)."""
        if not spice_level_table:
            return []
        return [
            level for level, overrides in spice_level_table.items()
            if all(name in owned_names for name, amount in overrides.items() if amount != "0")
        ]

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

        try:
            generated, feedback = recipe_graph.run(
                recipe, payload.spice_level, payload.doneness, payload.substitutions
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail="Error: 레시피 생성 요청이 실패함") from e

        try:
            return {
                "status": "done",
                "menu": generated["menu"],
                "ingredients": generated["ingredients"],
                "steps": generated["steps"],
                "score": feedback.get("score"),
                "feedback": {
                    "score": feedback.get("score"),
                    "comment": feedback.get("comment", ""),
                    "issues": feedback.get("issues", []),
                    "suggestions": feedback.get("suggestions", []),
                },
            }
        except KeyError as e:
            raise HTTPException(status_code=502, detail="Error: 레시피 생성 결과를 해석하지 못함") from e
