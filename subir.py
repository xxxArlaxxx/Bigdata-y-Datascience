import pandas as pd
from pymongo import MongoClient

MONGODB_URI = "mongodb+srv://Test:WK3VITtncqnnjQrr@cluster0.mjng6tk.mongodb.net/?retryWrites=true&w=majority"

client = MongoClient(MONGODB_URI)
db = client['catalogo_peliculas']
collection = db['peliculas']

df = pd.read_csv('catalogo_peliculas.csv')

for _, row in df.iterrows():
    pelicula = {
        "title": row["title"],
        "year": int(row["year"]),
        "genre": row["genre"].split(","),
        "director": row["director"],
        "actors": row["actors"].split(","),
        "imdb_rating": float(row["imdb_rating"]),
        "plot": row["plot"]
    }
    collection.insert_one(pelicula)
    print(f'{pelicula["title"]} subida a MongoDB Atlas')

print("Catálogo subido exitosamente a MongoDB Atlas.")