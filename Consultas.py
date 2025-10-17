import pprint
from pymongo import MongoClient

MONGODB_URI = "mongodb+srv://Test:WK3VITtncqnnjQrr@cluster0.mjng6tk.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGODB_URI)
db = client['catalogo_peliculas']
collection = db['peliculas']

def consulta_genero():
    genero = input("¿Qué género quieres buscar? (Ejemplo: Acción): ")
    for peli in collection.find({"genre": genero}):
        pprint.pprint(peli)


def consulta_rating_mayor():
    rating = float(input("¿Desde qué rating mínimo buscas? (Ejemplo: 8): "))
    for peli in collection.find({"imdb_rating": {"$gt": rating}}):
        pprint.pprint(peli)

def consulta_director():
    director = input("¿De qué director buscas películas?: ")
    for peli in collection.find({"director": director}):
        pprint.pprint(peli)

def consulta_anios():
    anio_inicio = int(input("Año inicial: "))
    anio_final = int(input("Año final: "))
    for peli in collection.find({"year": {"$gte": anio_inicio, "$lte": anio_final}}):
        pprint.pprint(peli)

def consulta_actor():
    actor = input("¿Qué actor quieres buscar?: ")
    for peli in collection.find({"actors": actor}):
        pprint.pprint(peli)

def consulta_generos_count():
    pipeline = [
        {"$unwind": "$genre"},
        {"$group": {"_id": "$genre", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    for doc in collection.aggregate(pipeline):
        pprint.pprint(doc)

def consulta_rating_ordenado():
    for peli in collection.find().sort("imdb_rating", -1):
        pprint.pprint(peli)

def consulta_plot():
    palabra = input("¿Qué palabra debe aparecer en el plot?: ")
    for peli in collection.find({"plot": {"$regex": palabra, "$options": "i"}}):
        pprint.pprint(peli)

def consulta_multiples_generos():
    for peli in collection.find({"genre.1": {"$exists": True}}):
        pprint.pprint(peli)

def consulta_rating_rango():
    min_rating = float(input("Rating mínimo: "))
    max_rating = float(input("Rating máximo: "))
    for peli in collection.find({"imdb_rating": {"$gte": min_rating, "$lte": max_rating}}):
        pprint.pprint(peli)

menu = """
Elige una consulta:
1. Buscar películas por género
2. Películas con rating mayor a X
3. Películas de un director específico
4. Películas entre dos años
5. Películas que incluyan a un actor
6. Número de películas por género
7. Películas ordenadas por rating
8. Películas cuyo plot contiene una palabra
9. Películas con más de un género
10. Películas con rating en un rango
0. Salir
"""

acciones = {
    "1": consulta_genero,
    "2": consulta_rating_mayor,
    "3": consulta_director,
    "4": consulta_anios,
    "5": consulta_actor,
    "6": consulta_generos_count,
    "7": consulta_rating_ordenado,
    "8": consulta_plot,
    "9": consulta_multiples_generos,
    "10": consulta_rating_rango
}

while True:
    print(menu)
    opcion = input("Opción: ")
    if opcion == "0":
        print("¡Hasta luego!")
        break
    accion = acciones.get(opcion)
    if accion:
        accion()
    else:
        print("Opción inválida, intenta de nuevo.")