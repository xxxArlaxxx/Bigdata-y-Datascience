import argparse                          # Para parsear argumentos desde la línea de comandos
import logging                           # Para emitir mensajes informativos / warnings / errores
from pathlib import Path                 # Manejo cómodo de rutas de archivo (cross-platform)
import pandas as pd                      # Manipulación de datos tabulares (CSV -> DataFrame)
import numpy as np                       # Utilidades numéricas y NaN
from pymongo import MongoClient, UpdateOne  # Cliente MongoDB y operación para bulk upserts
import sys                               # Para terminar el programa con código de salida cuando corresponda

# Conexión a MongoDB (en mi entorno de desarrollo dejo aquí la cadena,
# pero en un despliegue real la leería desde una variable de entorno o un secret manager)
DEFAULT_MONGO_URI = "mongodb+srv://Test:WK3VITtncqnnjQrr@cluster0.mjng6tk.mongodb.net/?retryWrites=true&w=majority"

# Nombre por defecto del CSV que espero procesar
DEFAULT_CSV_NAME = "ThrowbackDataThursday Week 11 - Film Genre Stats.csv"

# Configuro el logging para ver mensajes informativos; usar DEBUG para más detalle durante pruebas
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalizo los nombres de columna:
    - Quito espacios sobrantes alrededor del nombre.
    - Mapeo nombres "humanos" a nombres consistentes en snake_case para usar en el código.
    """
    df = df.rename(columns=lambda c: c.strip())
    mapping = {
        "Genre": "genre",
        "Year": "year",
        "Movies Released": "movies_released",
        "Gross": "gross",
        "Tickets Sold": "tickets_sold",
        "Inflation-Adjusted Gross": "inflation_adjusted_gross",
        "Top Movie": "top_movie_title",
        "Top Movie Gross (That Year)": "top_movie_gross",
        "Top Movie Inflation-Adjusted Gross (That Year)": "top_movie_inflation_adjusted_gross"
    }
    df = df.rename(columns=mapping)
    return df

def to_numeric_cols(df: pd.DataFrame, cols):
    """
    Intento convertir las columnas indicadas a tipo numérico.
    Uso errors='coerce' para transformar valores inválidos en NaN y detectarlos luego.
    """
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def derive_fields(df: pd.DataFrame) -> pd.DataFrame:
    """
    Relleno nulos con valores razonables y creo campos derivados:
    - movies_released: nulos -> 0 (entero)
    - otras columnas numéricas: nulos -> mediana (para no distorsionar con 0 arbitrario)
    - gross_per_movie, tickets_per_movie: calculados solo cuando movies_released > 0
    - decade: construcción simple a partir de year (p. ej. 1994 -> "1990s")
    - limpio top_movie_title quitando espacios sobrantes
    """
    cols_to_check = [
        "movies_released", "gross", "tickets_sold", "inflation_adjusted_gross",
        "top_movie_gross", "top_movie_inflation_adjusted_gross"
    ]
    for c in cols_to_check:
        if c in df.columns:
            if df[c].isna().any():
                if c == "movies_released":
                    # Para el número de películas supongo 0 si falta el dato (puedo cambiar esto si prefieres None)
                    df[c] = df[c].fillna(0).astype(int)
                else:
                    # Relleno con la mediana para mantener distribuciones razonables
                    df[c] = df[c].fillna(df[c].median())

    # Evito división por cero: si movies_released no existe o es 0 -> NaN
    df["gross_per_movie"] = df.apply(
        lambda r: (r["gross"] / r["movies_released"]) if ("movies_released" in r and r["movies_released"] and r["movies_released"] > 0) else np.nan,
        axis=1
    )
    df["tickets_per_movie"] = df.apply(
        lambda r: (r["tickets_sold"] / r["movies_released"]) if ("movies_released" in r and r["movies_released"] and r["movies_released"] > 0) else np.nan,
        axis=1
    )

    # Construyo decade de forma sencilla; asumo que 'year' es numérico o NaN
    df["decade"] = df["year"].apply(lambda y: f"{int(y)//10*10}s" if not pd.isna(y) else None)

    # Aseguro que el título de la película top sea string limpio
    if "top_movie_title" in df.columns:
        df["top_movie_title"] = df["top_movie_title"].astype(str).str.strip()
    return df

def row_to_doc(row: pd.Series) -> dict:
    """
    Armo el documento (modelo documental) que guardaré en MongoDB para cada fila.
    Diseño la estructura aquí de forma explícita para que sea fácil de entender y modificar.
    """
    doc = {
        "genre": row["genre"],
        # year puede ser None si no hay valor válido
        "year": int(row["year"]) if not pd.isna(row["year"]) else None,
        "movies_released": int(row["movies_released"]) if not pd.isna(row["movies_released"]) else 0,
        "gross": float(row["gross"]) if not pd.isna(row["gross"]) else 0.0,
        "tickets_sold": float(row["tickets_sold"]) if not pd.isna(row["tickets_sold"]) else 0.0,
        "inflation_adjusted_gross": float(row["inflation_adjusted_gross"]) if not pd.isna(row["inflation_adjusted_gross"]) else 0.0,
        # Subdocumento con la película principal de ese género-año
        "top_movie": {
            "title": row.get("top_movie_title", "") or "",
            # Si no hay valor explícito uso None (semántica: desconocido)
            "gross": float(row.get("top_movie_gross", 0)) if not pd.isna(row.get("top_movie_gross", None)) else None,
            "inflation_adjusted_gross": float(row.get("top_movie_inflation_adjusted_gross", 0)) if not pd.isna(row.get("top_movie_inflation_adjusted_gross", None)) else None
        },
        # Subdocumento con métricas derivadas
        "derived": {
            "gross_per_movie": None if pd.isna(row.get("gross_per_movie", None)) else float(row["gross_per_movie"]),
            "tickets_per_movie": None if pd.isna(row.get("tickets_per_movie", None)) else float(row["tickets_per_movie"]),
            "decade": row.get("decade", "")
        }
    }
    return doc

def etl(csv_path: Path, mongo_uri: str, db_name: str, collection_name: str, batch_size: int = 500):
    """
    Implemento el proceso ETL:
    - Extract: leer CSV con pandas
    - Transform: limpiar/normalizar columnas, convertir tipos y crear campos derivados
    - Load: escribir/upsertar en MongoDB con operaciones bulk para eficiencia
    """
    # Verifico que el CSV exista y doy un mensaje claro si no
    if not csv_path.exists():
        logging.error("Archivo CSV no encontrado: %s", csv_path)
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    logging.info("Leyendo CSV: %s", csv_path)
    # ---------- EXTRACT ----------
    df = pd.read_csv(csv_path)

    # ---------- TRANSFORM ----------
    df = clean_column_names(df)  # nombres consistentes
    to_numeric_cols(df, [
        "year", "movies_released", "gross", "tickets_sold",
        "inflation_adjusted_gross", "top_movie_gross", "top_movie_inflation_adjusted_gross"
    ])
    df = derive_fields(df)  # nulos razonables y campos derivados

    # ---------- LOAD ----------
    # Conecto a MongoDB; en futuros cambios puedo usar un context manager o reconexión automática
    client = MongoClient(mongo_uri)
    db = client[db_name]
    coll = db[collection_name]

    logging.info("Creando índices en collection %s.%s", db_name, collection_name)
    try:
        # Índices simples para acelerar consultas por género o año
        coll.create_index([("genre", 1)])
        coll.create_index([("year", 1)])
        # Índice único compuesto para evitar duplicados (genre, year)
        coll.create_index([("genre", 1), ("year", 1)], unique=True, name="genre_year_unique")
    except Exception as e:
        # Si algo falla aquí, no detengo el ETL; sólo informo.
        logging.warning("Error creando índices (puede que ya existan): %s", e)

    ops = []
    total = len(df)
    logging.info("Preparando upserts para %d documentos", total)

    # Itero fila a fila transformando cada una en un UpdateOne para bulk_write
    for _, row in df.iterrows():
        # Requiero género y año para la llave compuesta; si faltan salto la fila
        if pd.isna(row.get("genre")) or pd.isna(row.get("year")):
            logging.debug("Saltando fila sin género o año: %s", row.to_dict())
            continue

        doc = row_to_doc(row)
        filter_q = {"genre": doc["genre"], "year": doc["year"]}
        update = {"$set": doc}
        ops.append(UpdateOne(filter_q, update, upsert=True))

        # Cuando alcanzo el tamaño de batch, ejecuto el bulk_write por eficiencia
        if len(ops) >= batch_size:
            result = coll.bulk_write(ops)
            logging.info(
                "Bulk write ejecutado. matched=%d upserted=%d modified=%d",
                getattr(result, "matched_count", 0),
                getattr(result, "upserted_count", 0),
                getattr(result, "modified_count", 0)
            )
            ops = []  # limpio la lista para el próximo lote

    # Ejecutar cualquier operación restante
    if ops:
        result = coll.bulk_write(ops)
        logging.info(
            "Bulk final ejecutado. matched=%d upserted=%d modified=%d",
            getattr(result, "matched_count", 0),
            getattr(result, "upserted_count", 0),
            getattr(result, "modified_count", 0)
        )

    # Cierro client para liberar recursos de red/conexión
    try:
        client.close()
    except Exception:
        logging.debug("Error cerrando MongoClient (no crítico).")

    logging.info("ETL completado. Total procesados: %d", total)

def main():
    """
    Punto de entrada. Parseo argumentos y lanzo el ETL.
    """
    parser = argparse.ArgumentParser(description="ETL pipeline CSV -> MongoDB for genre stats")
    parser.add_argument("--csv", default=DEFAULT_CSV_NAME, help=f"Path al CSV (default = {DEFAULT_CSV_NAME})")
    parser.add_argument("--mongo-uri", default=DEFAULT_MONGO_URI, help="MongoDB URI (en producción leer desde ENV)")
    parser.add_argument("--db", default="etl_lab", help="Nombre DB")
    parser.add_argument("--collection", default="genre_stats", help="Nombre coleccion")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    try:
        etl(csv_path, args.mongo_uri, args.db, args.collection)
    except FileNotFoundError as e:
        logging.error(e)
        sys.exit(2)
    except Exception as e:
        logging.exception("Error durante ETL: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    main()





