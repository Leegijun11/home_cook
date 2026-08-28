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
