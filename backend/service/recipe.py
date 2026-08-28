from sqlalchemy.orm import Session
from crud.category import CategoryCrud
from crud.ingredients import IngredientCrud
from crud.recipe import RecipeCrud
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
