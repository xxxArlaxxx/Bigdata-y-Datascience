import argparse                          # Importa utilidades para leer parámetros desde la línea de comandos (CLI)
import logging                           # Importa el sistema de logging para INFO/WARN/ERROR/DEBUG
from pathlib import Path                 # Path ofrece manejo de rutas multiplataforma (Windows/Linux/Mac)
import pandas as pd                      # Pandas: lectura de CSV y manipulación tabular (DataFrame)
import numpy as np                       # NumPy: operaciones numéricas y manejo de NaN
from pymongo import MongoClient, UpdateOne  # Cliente de MongoDB y operación de actualización/insert en lote (upsert)
import sys                               # Funciones del intérprete (salir con códigos de estado, etc.)

# Conexión a MongoDB (en mi entorno de desarrollo dejo aquí la cadena,
# pero en un despliegue real la leería desde una variable de entorno o un secret manager)
DEFAULT_MONGO_URI = "mongodb+srv://Test:WK3VITtncqnnjQrr@cluster0.mjng6tk.mongodb.net/?retryWrites=true&w=majority"  # URI por defecto de MongoDB Atlas

# Nombre por defecto del CSV que espero procesar
DEFAULT_CSV_NAME = "ThrowbackDataThursday Week 11 - Film Genre Stats.csv"  # Archivo CSV por defecto si no se pasa --csv

# Configuro el logging para ver mensajes informativos; usar DEBUG para más detalle durante pruebas
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")  # Inicializa formato y nivel de logs

def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalizo los nombres de columna:
    - Quito espacios sobrantes alrededor del nombre.
    - Mapeo nombres "humanos" a nombres consistentes en snake_case para usar en el código.
    """
    df = df.rename(columns=lambda c: c.strip())  # Elimina espacios al inicio/fin de cada nombre de columna
    mapping = {                                 # Diccionario: nombre original -> nombre normalizado (snake_case)
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
    df = df.rename(columns=mapping)             # Renombra las columnas aplicando el mapeo
    return df                                   # Devuelve el DataFrame con cabeceras consistentes

def to_numeric_cols(df: pd.DataFrame, cols):
    """
    Intento convertir las columnas indicadas a tipo numérico.
    Uso errors='coerce' para transformar valores inválidos en NaN y detectarlos luego.
    """
    for c in cols:                              # Recorre la lista de columnas que deben ser numéricas
        if c in df.columns:                     # Solo actúa si la columna existe en el DataFrame
            df[c] = pd.to_numeric(df[c], errors="coerce")  # Convierte a número; no convertibles -> NaN
    return df                                   # Devuelve el DataFrame con columnas tipificadas

def derive_fields(df: pd.DataFrame) -> pd.DataFrame:
    """
    Relleno nulos con valores razonables y creo campos derivados:
    - movies_released: nulos -> 0 (entero)
    - otras columnas numéricas: nulos -> mediana (para no distorsionar con 0 arbitrario)
    - gross_per_movie, tickets_per_movie: calculados solo cuando movies_released > 0
    - decade: construcción simple a partir de year (p. ej. 1994 -> "1990s")
    - limpio top_movie_title quitando espacios sobrantes
    """
    cols_to_check = [                           # Lista de columnas donde evaluar e imputar nulos
        "movies_released", "gross", "tickets_sold", "inflation_adjusted_gross",
        "top_movie_gross", "top_movie_inflation_adjusted_gross"
    ]
    for c in cols_to_check:                     # Itera por cada columna a revisar
        if c in df.columns:                     # Verifica que la columna exista
            if df[c].isna().any():              # Si hay algún NaN en la columna
                if c == "movies_released":      # Caso especial: cantidad de películas
                    # Para el número de películas supongo 0 si falta el dato (puedo cambiar esto si prefieres None)
                    df[c] = df[c].fillna(0).astype(int)  # Imputa 0 y fuerza tipo entero
                else:
                    # Relleno con la mediana para mantener distribuciones razonables
                    df[c] = df[c].fillna(df[c].median())  # Imputa con mediana (robusto a outliers)

    # Evito división por cero: si movies_released no existe o es 0 -> NaN
    df["gross_per_movie"] = df.apply(           # Crea el promedio de recaudación por película
        lambda r: (r["gross"] / r["movies_released"]) if ("movies_released" in r and r["movies_released"] and r["movies_released"] > 0) else np.nan,
        axis=1                                  # Aplica por fila
    )
    df["tickets_per_movie"] = df.apply(         # Crea el promedio de tickets por película
        lambda r: (r["tickets_sold"] / r["movies_released"]) if ("movies_released" in r and r["movies_released"] and r["movies_released"] > 0) else np.nan,
        axis=1
    )

    # Construyo decade de forma sencilla; asumo que 'year' es numérico o NaN
    df["decade"] = df["year"].apply(lambda y: f"{int(y)//10*10}s" if not pd.isna(y) else None)  # Calcula década estilo "1990s"

    # Aseguro que el título de la película top sea string limpio
    if "top_movie_title" in df.columns:                     # Solo si existe la columna de título
        df["top_movie_title"] = df["top_movie_title"].astype(str).str.strip()  # Fuerza string y elimina espacios extra
    return df                                               # Devuelve el DataFrame enriquecido y sin nulos críticos

def row_to_doc(row: pd.Series) -> dict:
    """
    Armo el documento (modelo documental) que guardaré en MongoDB para cada fila.
    Diseño la estructura aquí de forma explícita para que sea fácil de entender y modificar.
    """
    doc = {                                                # Crea un diccionario con la forma final del documento Mongo
        "genre": row["genre"],                             # Género (texto)
        # year puede ser None si no hay valor válido
        "year": int(row["year"]) if not pd.isna(row["year"]) else None,  # Año como entero o None si falta
        "movies_released": int(row["movies_released"]) if not pd.isna(row["movies_released"]) else 0,  # Cantidad de películas
        "gross": float(row["gross"]) if not pd.isna(row["gross"]) else 0.0,                             # Recaudación nominal
        "tickets_sold": float(row["tickets_sold"]) if not pd.isna(row["tickets_sold"]) else 0.0,       # Tickets vendidos
        "inflation_adjusted_gross": float(row["inflation_adjusted_gross"]) if not pd.isna(row["inflation_adjusted_gross"]) else 0.0,  # Recaudación ajustada
        # Subdocumento con la película principal de ese género-año
        "top_movie": {                                     # Subdocumento con datos del “top movie”
            "title": row.get("top_movie_title", "") or "", # Título como string; si falta, cadena vacía
            # Si no hay valor explícito uso None (semántica: desconocido)
            "gross": float(row.get("top_movie_gross", 0)) if not pd.isna(row.get("top_movie_gross", None)) else None,  # Gross del top movie o None
            "inflation_adjusted_gross": float(row.get("top_movie_inflation_adjusted_gross", 0)) if not pd.isna(row.get("top_movie_inflation_adjusted_gross", None)) else None  # Gross ajustado o None
        },
        # Subdocumento con métricas derivadas
        "derived": {                                       # Subdocumento con campos calculados
            "gross_per_movie": None if pd.isna(row.get("gross_per_movie", None)) else float(row["gross_per_movie"]),      # Promedio gross por película
            "tickets_per_movie": None if pd.isna(row.get("tickets_per_movie", None)) else float(row["tickets_per_movie"]),# Promedio tickets por película
            "decade": row.get("decade", "")                # Década (string) o vacío si falta
        }
    }
    return doc                                              # Retorna el documento listo para escritura

def etl(csv_path: Path, mongo_uri: str, db_name: str, collection_name: str, batch_size: int = 500):
    """
    Implemento el proceso ETL:
    - Extract: leer CSV con pandas
    - Transform: limpiar/normalizar columnas, convertir tipos y crear campos derivados
    - Load: escribir/upsertar en MongoDB con operaciones bulk para eficiencia
    """
    # Verifico que el CSV exista y doy un mensaje claro si no
    if not csv_path.exists():                               # Chequea que la ruta del CSV exista
        logging.error("Archivo CSV no encontrado: %s", csv_path)  # Log de error si no está
        raise FileNotFoundError(f"CSV file not found: {csv_path}")  # Corta la ejecución con excepción clara

    logging.info("Leyendo CSV: %s", csv_path)               # Log informativo de inicio de lectura
    # ---------- EXTRACT ----------
    df = pd.read_csv(csv_path)                              # Lee el archivo CSV a un DataFrame

    # ---------- TRANSFORM ----------
    df = clean_column_names(df)  # nombres consistentes      # Normaliza cabeceras a snake_case
    to_numeric_cols(df, [                                     # Convierte columnas críticas a numéricas (NaN si no se puede)
        "year", "movies_released", "gross", "tickets_sold",
        "inflation_adjusted_gross", "top_movie_gross", "top_movie_inflation_adjusted_gross"
    ])
    df = derive_fields(df)  # nulos razonables y campos derivados  # Imputa nulos, crea derivados y limpia textos

    # ---------- LOAD ----------
    # Conecto a MongoDB; en futuros cambios puedo usar un context manager o reconexión automática
    client = MongoClient(mongo_uri)                         # Instancia el cliente de MongoDB con la URI
    db = client[db_name]                                    # Selecciona la base de datos
    coll = db[collection_name]                              # Selecciona la colección destino

    logging.info("Creando índices en collection %s.%s", db_name, collection_name)  # Anuncia creación de índices
    try:
        # Índices simples para acelerar consultas por género o año
        coll.create_index([("genre", 1)])                   # Índice por genre para filtros y agrupaciones
        coll.create_index([("year", 1)])                    # Índice por year para consultas temporales
        # Índice único compuesto para evitar duplicados (genre, year)
        coll.create_index([("genre", 1), ("year", 1)], unique=True, name="genre_year_unique")  # Garantiza unicidad por par género–año
    except Exception as e:
        # Si algo falla aquí, no detengo el ETL; sólo informo.
        logging.warning("Error creando índices (puede que ya existan): %s", e)  # Advertencia si el índice ya existe u otro error no crítico

    ops = []                                                # Acumula operaciones UpdateOne para ejecutar en lote
    total = len(df)                                         # Conteo de filas a procesar
    logging.info("Preparando upserts para %d documentos", total)  # Log de preparación

    # Itero fila a fila transformando cada una en un UpdateOne para bulk_write
    for _, row in df.iterrows():                            # Recorre cada fila del DataFrame
        # Requiero género y año para la llave compuesta; si faltan salto la fila
        if pd.isna(row.get("genre")) or pd.isna(row.get("year")):  # Si falta clave lógica (genre o year) no se procesa
            logging.debug("Saltando fila sin género o año: %s", row.to_dict())  # Log de depuración para diagnóstico
            continue                                         # Salta a la siguiente fila

        doc = row_to_doc(row)                                # Convierte la fila en documento destino
        filter_q = {"genre": doc["genre"], "year": doc["year"]}  # Filtro de coincidencia para upsert (clave lógica)
        update = {"$set": doc}                               # Operación: actualizar todo el documento con los campos actuales
        ops.append(UpdateOne(filter_q, update, upsert=True)) # Agrega la operación de upsert al lote

        # Cuando alcanzo el tamaño de batch, ejecuto el bulk_write por eficiencia
        if len(ops) >= batch_size:                           # Si el lote alcanzó el tamaño definido
            result = coll.bulk_write(ops)                    # Ejecuta las operaciones en el servidor
            logging.info(                                    # Reporta métricas del lote (coincididos, insertados, modificados)
                "Bulk write ejecutado. matched=%d upserted=%d modified=%d",
                getattr(result, "matched_count", 0),
                getattr(result, "upserted_count", 0),
                getattr(result, "modified_count", 0)
            )
            ops = []  # limpio la lista para el próximo lote   # Reinicia el acumulador de operaciones

    # Ejecutar cualquier operación restante
    if ops:                                                  # Si quedaron operaciones sin ejecutar tras el bucle
        result = coll.bulk_write(ops)                        # Ejecuta el último lote
        logging.info(                                        # Reporta métricas del “bulk” final
            "Bulk final ejecutado. matched=%d upserted=%d modified=%d",
            getattr(result, "matched_count", 0),
            getattr(result, "upserted_count", 0),
            getattr(result, "modified_count", 0)
        )

    # Cierro client para liberar recursos de red/conexión
    try:
        client.close()                                       # Intenta cerrar la conexión a MongoDB
    except Exception:
        logging.debug("Error cerrando MongoClient (no crítico).")  # Si falla el cierre, lo registra como no crítico

    logging.info("ETL completado. Total procesados: %d", total)    # Log final indicando cuántas filas se procesaron

def main():
    """
    Punto de entrada. Parseo argumentos y lanzo el ETL.
    """
    parser = argparse.ArgumentParser(description="ETL pipeline CSV -> MongoDB for genre stats")  # Crea el parser de argumentos CLI
    parser.add_argument("--csv", default=DEFAULT_CSV_NAME, help=f"Path al CSV (default = {DEFAULT_CSV_NAME})")  # Argumento: ruta del CSV
    parser.add_argument("--mongo-uri", default=DEFAULT_MONGO_URI, help="MongoDB URI (en producción leer desde ENV)")  # Argumento: URI de MongoDB
    parser.add_argument("--db", default="etl_lab", help="Nombre DB")                       # Argumento: nombre de la base de datos
    parser.add_argument("--collection", default="genre_stats", help="Nombre coleccion")    # Argumento: nombre de la colección
    args = parser.parse_args()                                                             # Parsea los argumentos entregados por el usuario

    csv_path = Path(args.csv)                                                              # Convierte la ruta del CSV a objeto Path
    try:
        etl(csv_path, args.mongo_uri, args.db, args.collection)                            # Ejecuta el pipeline ETL con los parámetros
    except FileNotFoundError as e:                                                         # Captura error de archivo no encontrado
        logging.error(e)                                                                   # Loguea el error
        sys.exit(2)                                                                        # Sale del programa con código 2 (error esperado)
    except Exception as e:                                                                 # Captura cualquier otra excepción
        logging.exception("Error durante ETL: %s", e)                                      # Loguea con stacktrace para diagnóstico
        sys.exit(1)                                                                        # Sale con código 1 (error general)

if __name__ == "__main__":                                                                 # Ejecuta solo si el script se corre directamente
    main()                                                                                 # Llama a main() para iniciar el proceso