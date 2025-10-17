import pandas as pd
import random
from faker import Faker

fake = Faker('es_ES')


generos = [
    "Acción", "Comedia", "Drama", "Aventura", "Ciencia", "Romance",
    "Terror", "Thriller", "Familiar", "Sci-Fi", "Misterio"
]
plots_base = [
    "Una increíble aventura en tierras desconocidas.",
    "El protagonista enfrenta un gran desafío.",
    "Un grupo de amigos se embarca en una misión peligrosa.",
    "La familia se reúne para resolver un misterio.",
    "Un científico loco crea una invención inesperada.",
    "El héroe debe salvar a la ciudad.",
    "Un romance surge en circunstancias improbables.",
    "Un viaje cambia la vida de todos.",
    "La verdad sale a la luz en el momento menos esperado.",
    "Un enemigo acecha en la oscuridad."
]
anios = list(range(2000, 2024))

def generar_pelicula():
    title = fake.sentence(nb_words=3).replace('.', '')
    year = random.choice(anios)
    genre = ",".join(random.sample(generos, random.randint(1, 3)))
    director = fake.name()
    actors = ", ".join([fake.name() for _ in range(random.randint(2, 4))])
    imdb_rating = round(random.uniform(6.0, 9.5), 1)
    plot = random.choice(plots_base)
    return {
        "title": title,
        "year": year,
        "genre": genre,
        "director": director,
        "actors": actors,
        "imdb_rating": imdb_rating,
        "plot": plot
    }
peliculas = [generar_pelicula() for _ in range(10)]
df = pd.DataFrame(peliculas)
df.to_csv("catalogo_peliculas.csv", index=False)
print("Catálogo de películas aleatorio generado en catalogo_peliculas.csv")