from functools import lru_cache
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
    @lru_cache(maxsize=1)
    def _load_index():
        """레시피 파일을 한 번만 읽어 (목록, recipe_ref 딕셔너리)로 보관한다.

        get_by_ref가 호출될 때마다 파일 전체를 다시 읽고 YAML 파싱하던 것이 병목이었다
        (자연어 검색 1회에 get_by_ref 10번, 로컬 측정 약 1.7초). 호출하는 쪽에서 레시피
        dict를 수정하지 않으므로 같은 객체를 공유해도 안전하다. 레시피 md를 고치면
        서버를 재시작하거나 RecipeCrud._load_index.cache_clear()를 호출해야 반영된다.
        """
        recipes = [
            RecipeCrud._parse_recipe_file(path)
            for path in sorted(RECIPES_DIR.glob("**/*.md"))
        ]
        return recipes, {recipe["recipe_ref"]: recipe for recipe in recipes}

    @staticmethod
    def load_all_recipes():
        return RecipeCrud._load_index()[0]

    @staticmethod
    def find_matching_recipes(cuisine: str, dish_type: str):
        recipes = RecipeCrud.load_all_recipes()
        return [
            recipe for recipe in recipes
            if recipe.get("cuisine") == cuisine and recipe.get("dish_type") == dish_type
        ]

    @staticmethod
    def get_by_ref(recipe_ref: str):
        return RecipeCrud._load_index()[1].get(recipe_ref)
