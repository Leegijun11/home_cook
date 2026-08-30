from pydantic import BaseModel



# 재료 전체 정보 반환용
class IngredientOut(BaseModel):
    id:int
    name:str
    category:str
    type:str
    owned:bool

    class Config:
        from_attributes = True


# 카테고리 선택 값
class CategorySelect(BaseModel):
    cuisine: str #"양식, 일식, .."
    dish_type: str # "면류, 밥류, ..."