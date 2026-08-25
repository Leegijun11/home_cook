import pandas as pd
from database import SessionLocal
from model.ingredients import Ingredients


df = pd.read_csv(r"C:\Users\hi\Desktop\home_cooking\ingredients_seed.csv")


print(df["owned"].dtype)

db =SessionLocal()
db.bulk_insert_mappings(Ingredients, df.to_dict(orient="records"))
db.commit()
