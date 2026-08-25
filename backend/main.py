from fastapi import FastAPI
from database import engine, Base
from model.ingredients import Ingredients
app = FastAPI()


@app.get("/")
def health():
    return {"msg":"health check"}


Base.metadata.create_all(bind=engine)