from pathlib import Path

import pandas as pd
from sqlalchemy import select
from database import SessionLocal
from model.ingredients import Ingredients

CSV_PATH = Path(__file__).resolve().parent.parent / "ingredients_seed.csv"
df = pd.read_csv(CSV_PATH)


print(df["owned"].dtype)

db = SessionLocal()
existing_names = {row[0] for row in db.execute(select(Ingredients.name))}
new_rows = df[~df["name"].isin(existing_names)]

db.bulk_insert_mappings(Ingredients, new_rows.to_dict(orient="records"))
db.commit()
