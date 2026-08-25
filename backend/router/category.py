from sqlalchemy.orm import Session
from fastapi import APIRouter,Depends
from database import get_db
from service.category import CategoryService
from schema.category import CategorySelect

router = APIRouter(prefix="/category")


@router.post("/")
def post_category(category:CategorySelect, db:Session=Depends(get_db)):
    return CategoryService.post_category(category,db)


@router.get("/{id}")
def get_category(category_id:int, db:Session=Depends(get_db)):
    return CategoryService.get_category(category_id,db)