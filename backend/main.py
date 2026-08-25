from fastapi import FastAPI
from database import engine, Base
from model.ingredients import Ingredients
from router.ingredients import router
app = FastAPI()


@app.get("/")
def health():
    return {"msg":"health check"}

app.include_router(router)
Base.metadata.create_all(bind=engine)