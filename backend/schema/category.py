from pydantic import BaseModel


# 카테고리 선택 값
class CategorySelect(BaseModel):
    cuisine: str #"양식, 일식, .."
    dish_type: str # "면류, 밥류, ..."