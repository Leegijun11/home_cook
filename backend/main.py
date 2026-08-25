from fastapi import FastAPI
from database import engine, Base
from model.ingredients import Ingredients
from model.category import Category
from router.ingredients import router as ingredient_router
from router.category import router as category_router
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
@app.get("/")
def health():
    return {"msg":"health check"}

app.include_router(ingredient_router)
app.include_router(category_router)
Base.metadata.create_all(bind=engine)