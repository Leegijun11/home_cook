from sqlalchemy.orm import Session
from crud.ingredients import IngredientCrud
from fastapi import HTTPException


class IngredientService:


    @staticmethod
    def get_ingredients(db:Session):
        result = IngredientCrud.get_ingredients(db)
        if result is None :
            raise HTTPException(status_code=404, detail= "Error: 재료 전체 리스트가 로드되지 않음")
        return result


    @staticmethod
    def toggle_ingredient(id:int, owned:bool, db:Session):
        result = IngredientCrud.toggle_ingredient(id, owned, db)
        if result is None:
            raise HTTPException(status_code=404, detail="Error:재료 선택이 되지 않았음. owned가 여전히 false")
        return result