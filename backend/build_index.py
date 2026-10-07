from crud.recipe import RecipeCrud
from vectorstore import chroma_store

recipes = RecipeCrud.load_all_recipes()
indexed_count = chroma_store.rebuild_index(recipes)

print(f"전체 레시피 {len(recipes)}개 중 {indexed_count}개를 벡터 색인(ChromaDB)에 저장했습니다.")
