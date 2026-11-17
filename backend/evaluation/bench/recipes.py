"""레시피 md 파일을 읽어 검색용 레코드로 만든다 (DB 없이 평가하기 위함)."""
import re
from pathlib import Path
import yaml

RECIPES_DIR = Path(__file__).resolve().parents[2] / "recipes"


def load_recipes(recipes_dir: Path = RECIPES_DIR):
    recipes = []
    for path in sorted(recipes_dir.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, flags=re.DOTALL)
        if not match:
            continue
        meta = yaml.safe_load(match.group(1)) or {}
        body = match.group(2).strip()
        cuisine = meta.get("cuisine") or path.parts[-3]
        folder_dish_type = path.parts[-2]
        name = meta.get("name") or path.stem
        recipes.append(
            {
                # eval_cases.py 의 정답 표기와 같은 형식: 요리분류_종류_이름 (종류는 폴더명)
                "recipe_ref": f"{cuisine}_{folder_dish_type}_{name}",
                "name": name,
                "cuisine": cuisine,
                "dish_type": meta.get("dish_type") or "",
                "embedding_text": meta.get("embedding_text") or "",
                "base_ingredients": meta.get("base_ingredients") or [],
                "body": body,
            }
        )
    return recipes
