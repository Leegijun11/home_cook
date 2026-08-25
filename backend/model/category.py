from sqlalchemy import Column, String, Integer
from database import Base


class Category(Base):
    __tablename__ = "category"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cuisine = Column(String(100), nullable=True)
    dish_type = Column(String(100), nullable=True)