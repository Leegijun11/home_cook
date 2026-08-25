from pydantic import BaseModel
from typing import Optional



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


# 원래 재료와 대체 재료 + 이유 (llm)
class Substitution(BaseModel):
    original : str
    replacement : str
    reason : Optional[str] =  None


# 생성된 레시피 
class GeneratedReciped(BaseModel):
    menu : str
    ingredients : list[str]
    steps : str
    Substitutions : list[Substitution] = []


# 미식가 평가
class CriticFeedback(BaseModel):
    score: float
    issues: list[str] = []
    suggestions: list[str] = []

# 최종평가
class RecipeGenerateResponse(BaseModel):
    status : str # 추천 / 비추천
    recipe : Optional[GeneratedReciped] = None
    feedback: Optional[CriticFeedback] = None
    message : Optional[str] = None