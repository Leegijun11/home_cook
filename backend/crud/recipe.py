from pathlib import Path
import yaml

RECIPES_DIR = Path(__file__).resolve().parent.parent / "recipes"


class RecipeCrud:

    @staticmethod
    def _parse_recipe_file(path: Path):
        text = path.read_text(encoding="utf-8")
        _, frontmatter, body = text.split("---", 2)
        data = yaml.safe_load(frontmatter) or {}

        relative_parts = path.relative_to(RECIPES_DIR).with_suffix("").parts
        data["recipe_ref"] = "_".join(relative_parts)
        data["steps"] = body.replace("## 조리방법", "", 1).strip()
        return data

    @staticmethod
    def load_all_recipes():
        return [
            RecipeCrud._parse_recipe_file(path)
            for path in sorted(RECIPES_DIR.glob("**/*.md"))
        ]

    @staticmethod
    def find_matching_recipes(cuisine: str, dish_type: str):
        recipes = RecipeCrud.load_all_recipes()
        return [
            recipe for recipe in recipes
            if recipe.get("cuisine") == cuisine and recipe.get("dish_type") == dish_type
        ]

    @staticmethod
    def get_by_ref(recipe_ref: str):
        for recipe in RecipeCrud.load_all_recipes():
            if recipe["recipe_ref"] == recipe_ref:
                return recipe
        return None
