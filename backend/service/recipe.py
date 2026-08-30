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
            generated, feedback = recipe_graph.run(recipe, payload.spice_level, payload.doneness)
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
                    "issues": feedback.get("issues", []),
                    "suggestions": feedback.get("suggestions", []),
                },
            }
        except KeyError as e:
            raise HTTPException(status_code=502, detail="Error: 레시피 생성 결과를 해석하지 못함") from e
