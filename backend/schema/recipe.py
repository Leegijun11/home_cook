from pydantic import BaseModel
from typing import Optional


# 레시피 후보 확정 요청
class CandidateRequest(BaseModel):
    category_id: int


# 레시피 후보 확정 응답
class CandidateResponse(BaseModel):
    status: str  # "ready" / "no_candidate"
    recipe_ref: Optional[str] = None
    menu: Optional[str] = None
    needs_spice: bool = False
    needs_doneness: bool = False
    spice_options: list[str] = []
    doneness_options: list[str] = []


# 레시피 생성 요청
class GenerateRequest(BaseModel):
    recipe_ref: str
    spice_level: Optional[str] = None
    doneness: Optional[str] = None


# 미식가 평가
class CriticFeedback(BaseModel):
    score: float
    comment: str = ""
    issues: list[str] = []
    suggestions: list[str] = []


# 레시피 생성 응답
class GenerateResponse(BaseModel):
    status: str  # "done"
    menu: str
    ingredients: list[str]
    steps: str
    score: Optional[float] = None
    feedback: Optional[CriticFeedback] = None
