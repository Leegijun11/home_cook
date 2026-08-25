from sqlalchemy.orm import Session
from sqlalchemy import select
from model.category import Category
from schema.ingredients import CategorySelect

class CategoryCrud:


    @staticmethod
    def post_category(category:CategorySelect, db:Session):
        user_category = Category(cuisine=category.cuisine, dish_type=category.dish_type)
        db.add(user_category)
        db.commit()
        db.refresh(user_category)
        return user_category


    @staticmethod
    def get_category(category_id:int, db:Session):
        result = db.execute(select(Category).where(Category.id == category_id))
        return result.scalar_one_or_none()