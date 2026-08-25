from fastapi import FastAPI
from database import engine, Base
from model.ingredients import Ingredients
from router.ingredients import router
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

app.include_router(router)
Base.metadata.create_all(bind=engine)