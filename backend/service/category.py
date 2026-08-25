from sqlalchemy.orm import Session
from schema.category import CategorySelect
from crud.category import CategoryCrud
from fastapi import HTTPException

class CategoryService:

    @staticmethod
    def post_category(category:CategorySelect, db:Session):
        result = CategoryCrud.post_category(category, db)
        if result is None:
            raise HTTPException(status_code=404, detail="저장하려고 고른 카테고리가 없음")


    @staticmethod
    def get_category(category_id:int, db:Session):
        result = CategoryCrud.get_category(category_id,db)
        if result is None:
            raise HTTPException(status_code=404, detail="저장된 카테고리가 하나가 아니거나, 없어서 가져오지 못함")

        