from sqlalchemy import Column, Integer, String, Date, Boolean
from database import Base


class Ingredients(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255))
    category = Column(String(100))
    type = Column(String(100))
    owned = Column(Boolean, default=False, nullable=False)

