from fastapi import APIRouter, Depends
from database import get_db
from sqlalchemy.orm import Session
from service.recipe import RecipeService
from schema.recipe import (
    CandidateRequest,
    CandidateResponse,
    SearchRequest,
    GenerateRequest,
    GenerateResponse,
)

router = APIRouter(prefix="/recipe")


@router.post("/candidate", response_model=CandidateResponse)
def get_recipe_candidate(req: CandidateRequest, db: Session = Depends(get_db)):
    return RecipeService.get_candidate(req.category_id, db)


@router.post("/search", response_model=CandidateResponse)
def search_recipe_candidate(req: SearchRequest, db: Session = Depends(get_db)):
    return RecipeService.search_candidate(req.query, db)


@router.post("/generate", response_model=GenerateResponse)
def generate_recipe(req: GenerateRequest):
    return RecipeService.generate(req)
