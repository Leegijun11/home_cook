from sqlalchemy.orm import Session
from sqlalchemy import select
from model.ingredients import Ingredients


class IngredientCrud:

    @staticmethod
    def get_ingredients(db:Session):
        result = db.execute(select(Ingredients))
        return result.scalars().all()


    @staticmethod
    def get_owned_ingredients(db:Session):
        result = db.execute(select(Ingredients).where(Ingredients.owned == True))
        return result.scalars().all()


    @staticmethod
    def toggle_ingredient(id:int, owned:bool, db:Session):
        result = db.execute(select(Ingredients).where(Ingredients.id==id))
        ingredient = result.scalar_one_or_none()


        if ingredient is None:
            return None

        ingredient.owned = owned
        db.commit()
        db.refresh(ingredient)


        return ingredient