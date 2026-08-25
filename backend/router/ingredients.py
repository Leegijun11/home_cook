from fastapi import APIRouter, Depends
from database import get_db
from sqlalchemy.orm import Session
from service.ingredients import IngredientService


router = APIRouter(prefix="/ingredient")


@router.get("/")
def get_ingredienets():
    pass



@router.post("/{id}")
def toggle_ingredient(id:int, owned:bool, db:Session=Depends(get_db)):
    return IngredientService.toggle_ingredient(id,owned,db)