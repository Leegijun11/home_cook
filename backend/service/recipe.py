from sqlalchemy.orm import Session
from crud.category import CategoryCrud
from crud.ingredients import IngredientCrud
from crud.recipe import RecipeCrud
from schema.recipe import GenerateRequest
from service import recipe_graph
from vectorstore import chroma_store
from fastapi import HTTPException


class RecipeService:

    @staticmethod
    def get_candidate(category_id: int, db: Session):
        category = CategoryCrud.get_category(category_id, db)
        if category is None:
            raise HTTPException(status_code=404, detail="Error: 선택된 카테고리를 찾을 수 없음")

        owned_names = {ingredient.name for ingredient in IngredientCrud.get_owned_ingredients(db)}
        candidates = RecipeCrud.find_matching_recipes(category.cuisine, category.dish_type)

        return RecipeService._first_makeable(candidates, owned_names) or {"status": "no_candidate"}

    @staticmethod
    def search_candidate(query: str, db: Session):
        """자연어 쿼리로 ChromaDB에서 의미적으로 가까운 레시피를 찾고,
        그중 지금 보유한 재료·도구로 실제로 만들 수 있는 첫 번째 후보를 반환한다."""
        owned_names = {ingredient.name for ingredient in IngredientCrud.get_owned_ingredients(db)}

        ranked_refs = chroma_store.search(query, n_results=10)
        candidates = [RecipeCrud.get_by_ref(ref) for ref in ranked_refs]
        candidates = [recipe for recipe in candidates if recipe is not None]

        return RecipeService._first_makeable(candidates, owned_names) or {"status": "no_candidate"}

    @staticmethod
    def _first_makeable(candidates: list, owned_names: set):
        """후보 레시피 목록을 순서대로 보면서, 지금 보유한 재료·도구로 만들 수 있는
        첫 번째 레시피를 찾아 candidate 응답 형태로 반환한다. 하나도 없으면 None."""
        for recipe in candidates:
            tool_substitution = RecipeService._resolve_tool(recipe, owned_names)
            if tool_substitution is None:
                continue

            substitutions = RecipeService._resolve_substitutions(recipe, owned_names)
            if substitutions is None:
                continue
            substitutions = {**substitutions, **tool_substitution}

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

        return None

    @staticmethod
    def _resolve_tool(recipe: dict, owned_names: set):
        """main_tool을 보유하고 있으면 그대로, 없으면 alt_tools 중 보유한 것을 찾는다.

        main_tool도 alt_tools도 보유하지 못했으면 이 레시피는 지금 조리도구로 불가능한
        것이므로 None을 반환. 대체가 필요 없으면 빈 dict, 대체했으면 {main_tool: 대체도구}.
        """
        main_tool = recipe.get("main_tool")
        if main_tool in owned_names:
            return {}
        alt_tools = recipe.get("alt_tools") or []
        replacement = next((tool for tool in alt_tools if tool in owned_names), None)
        if replacement is None:
            return None
        return {main_tool: replacement}

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
                    "strengths": feedback.get("strengths", []),
                    "issues": feedback.get("issues", []),
                    "suggestions": feedback.get("suggestions", []),
                },
            }
        except KeyError as e:
            raise HTTPException(status_code=502, detail="Error: 레시피 생성 결과를 해석하지 못함") from e
