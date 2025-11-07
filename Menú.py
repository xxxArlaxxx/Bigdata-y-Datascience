from pymongo import MongoClient  # Importa el cliente de MongoDB para conectarse a la base de datos
from pprint import pprint        # Importa pprint para imprimir estructuras de datos de forma legible
import argparse                  # Permite parsear argumentos desde la línea de comandos
from pathlib import Path         # Maneja rutas de archivos y directorios de forma portátil
import pandas as pd              # Biblioteca para manipulación y análisis de datos en tablas
import matplotlib.pyplot as plt  # Biblioteca base para generar gráficos
import seaborn as sns            # Capa de alto nivel sobre matplotlib para gráficos más estéticos
import os                        # Proporciona acceso a variables de entorno y utilidades del sistema
import sys                       # Proporciona funciones y variables del intérprete (ej. sys.exit)
import numpy as np               # Biblioteca de cálculo numérico (vectores, estadísticas, etc.)

DEFAULT_MONGO_URI = "mongodb+srv://Test:WK3VITtncqnnjQrr@cluster0.mjng6tk.mongodb.net/?retryWrites=true&w=majority"  # URI por defecto para conectarse a MongoDB (en prod, usar variable de entorno)

# ---------------------------
# Helper para guardar CSV
# ---------------------------
def save_list_of_dicts_as_csv(data, path: Path):  # Define una función para guardar una lista de diccionarios como CSV
    if not data:                                  # Si la lista está vacía, no hay nada que guardar
        print("No hay datos para guardar.")       # Informa al usuario que no hay datos
        return                                    # Sale de la función
    try:                                          # Intenta ejecutar el bloque de guardado
        df = pd.DataFrame(data)                   # Convierte la lista de dicts en un DataFrame de pandas
        df.to_csv(path, index=False)              # Escribe el DataFrame a un archivo CSV sin la columna de índice
        print(f"Guardado CSV: {path}")            # Informa la ruta donde se guardó el archivo
    except Exception as e:                         # Captura cualquier excepción que ocurra
        print("Error al guardar CSV:", e)         # Imprime el error producido

# ---------------------------
# Consultas (Agregaciones)
# ---------------------------
def total_inflation_adjusted_gross_per_genre(coll):  # Consulta: total de gross ajustado por género
    pipeline = [                                     # Define una tubería de agregación de MongoDB
        {"$group": {"_id": "$genre", "total_inflation_gross": {"$sum": "$inflation_adjusted_gross"}, "count": {"$sum": 1}}},  # Agrupa por género sumando el gross ajustado y contando filas
        {"$sort": {"total_inflation_gross": -1}}     # Ordena de mayor a menor por el total
    ]
    return list(coll.aggregate(pipeline))            # Ejecuta la agregación y devuelve los resultados como lista

def top_years_by_movies_released(coll, top_n=10):    # Consulta: años con más películas lanzadas
    pipeline = [                                     # Define la tubería de agregación
        {"$group": {"_id": "$year", "movies_total": {"$sum": "$movies_released"}}},  # Agrupa por año sumando las películas lanzadas
        {"$sort": {"movies_total": -1}},             # Ordena de mayor a menor
        {"$limit": top_n}                            # Limita a los top N años
    ]
    return list(coll.aggregate(pipeline))            # Ejecuta y devuelve la lista de resultados

def top_movies_overall(coll, top_n=10):              # Consulta: títulos que más aparecen como top_movie
    pipeline = [                                     # Define la tubería
        {"$match": {"top_movie.title": {"$exists": True, "$ne": ""}}},  # Filtra documentos que tienen título de top_movie no vacío
        {"$group": {"_id": "$top_movie.title", "max_gross": {"$max": "$top_movie.gross"}, "appearances": {"$sum": 1}}},  # Agrupa por título y calcula máximo gross y apariciones
        {"$sort": {"max_gross": -1}},                # Ordena por mayor recaudación del top_movie
        {"$limit": top_n}                            # Limita a los top N
    ]
    return list(coll.aggregate(pipeline))            # Devuelve resultados

def genres_with_highest_growth(coll, start_year=1995, end_year=2018, top_n=10):  # Consulta: géneros con mayor crecimiento entre dos años
    pipeline = [                                                                         # Define pipeline
        {"$match": {"year": {"$in": [start_year, end_year]}}},                           # Filtra solo filas de los años de interés
        {"$group": {"_id": {"genre": "$genre", "year": "$year"}, "total": {"$sum": "$inflation_adjusted_gross"}}},  # Suma gross ajustado por género-año
        {"$project": {"genre": "$_id.genre", "year": "$_id.year", "total": 1, "_id": 0}},  # Reestructura el documento para proyectar campos limpios
        {"$group": {"_id": "$genre", "values": {"$push": {"year": "$year", "total": "$total"}}}},                   # Agrupa por género y crea arreglo con (año, total)
        {"$project": {"genre": "$_id", "values": 1}},                                   # Proyecta el género y los valores
        {"$project": {                                                                   # Extrae los totales para start y end year
            "genre": 1,
            "start": {"$arrayElemAt": [{"$filter": {"input": "$values", "as": "v", "cond": {"$eq": ["$$v.year", start_year]}}}, 0]},
            "end": {"$arrayElemAt": [{"$filter": {"input": "$values", "as": "v", "cond": {"$eq": ["$$v.year", end_year]}}}, 0]}
        }},
        {"$project": {                                                                   # Calcula la razón de crecimiento end/start con control de divisiones por cero/nulos
            "genre": 1,
            "start_total": "$start.total",
            "end_total": "$end.total",
            "growth_ratio": {"$cond": [{"$and": [{"$gt": ["$start.total", 0]}, {"$ne": ["$start.total", None]}, {"$ne": ["$end.total", None]}]}, {"$divide": ["$end.total", "$start.total"]}, None]}
        }},
        {"$sort": {"growth_ratio": -1}},                                                 # Ordena por mayor crecimiento
        {"$limit": top_n}                                                                # Limita a top N
    ]
    return list(coll.aggregate(pipeline))                                                # Ejecuta y retorna la lista

def years_with_most_blockbusters(coll, threshold=300000000):  # Consulta: años con más blockbusters según umbral de top_movie.gross
    pipeline = [                                              # Define pipeline
        {"$match": {"top_movie.gross": {"$gte": threshold}}}, # Filtra documentos cuyo top_movie supera el umbral
        {"$group": {"_id": "$year", "count_blockbusters": {"$sum": 1}}},  # Cuenta cuántos géneros-año cumplen por año
        {"$sort": {"count_blockbusters": -1}}                 # Ordena por mayor cantidad
    ]
    return list(coll.aggregate(pipeline))                     # Retorna resultados

def bucket_movies_by_gross(coll, buckets=5):                  # Consulta: bucketing automático de gross ajustado
    pipeline = [                                              # Define pipeline
        {"$bucketAuto": {"groupBy": "$inflation_adjusted_gross", "buckets": buckets}}  # Usa $bucketAuto para dividir en 'buckets' con igual tamaño de muestra
    ]
    return list(coll.aggregate(pipeline))                     # Retorna resultados

def sample_records_for_genre(coll, genre, limit=20):          # Consulta: muestra de documentos para un género dado
    return list(coll.find({"genre": genre}).sort("year", 1).limit(limit))  # Busca por género, ordena por año ascendente y limita el número de documentos

def genres_movies_released_trend(coll, genre_list=None):      # Consulta: serie temporal de películas lanzadas por género
    if not genre_list:                                        # Si no se especifican géneros manualmente
        top_genres = [g["_id"] for g in list(coll.aggregate([ # Calcula los 5 géneros con mayor gross ajustado
            {"$group": {"_id": "$genre", "total": {"$sum": "$inflation_adjusted_gross"}}},
            {"$sort": {"total": -1}},
            {"$limit": 5}
        ]))]
    else:                                                     # Si se proporcionó lista de géneros
        top_genres = genre_list                               # Usa la lista recibida
    pipeline = [                                              # Define pipeline
        {"$match": {"genre": {"$in": top_genres}}},           # Filtra por los géneros seleccionados
        {"$group": {"_id": {"genre": "$genre", "year": "$year"}, "movies_released": {"$sum": "$movies_released"}}},  # Agrega por género-año
        {"$project": {"genre": "$_id.genre", "year": "$_id.year", "movies_released": 1, "_id": 0}},                 # Proyecta campos limpios
        {"$sort": {"year": 1}},                               # Ordena por año ascendente
        {"$group": {"_id": "$genre", "data": {"$push": {"year": "$year", "movies_released": "$movies_released"}}}}  # Reagrupa por género con su serie
    ]
    return list(coll.aggregate(pipeline))                     # Retorna la serie temporal por género

def revenue_per_ticket_stats(coll):                           # Consulta: estadística de revenue por ticket por género
    pipeline = [                                              # Define pipeline
        {"$match": {"tickets_sold": {"$gt": 0}}},             # Filtra documentos con tickets vendidos positivos
        {"$project": {"genre": 1, "revenue_per_ticket": {"$divide": ["$inflation_adjusted_gross", "$tickets_sold"]}}},  # Calcula revenue/ticket
        {"$group": {"_id": "$genre", "avg_rev_per_ticket": {"$avg": "$revenue_per_ticket"}, "count": {"$sum": 1}}},     # Promedia por género
        {"$sort": {"avg_rev_per_ticket": -1}}                 # Ordena por mayor promedio
    ]
    return list(coll.aggregate(pipeline))                     # Retorna resultados

# ---------------------------
# EDA helpers y gráficos de calidad
# ---------------------------
def detect_outliers_iqr(series):                              # Función auxiliar: detecta outliers univariados usando IQR
    q1 = series.quantile(0.25)                                # Calcula el cuartil 1 (Q1)
    q3 = series.quantile(0.75)                                # Calcula el cuartil 3 (Q3)
    iqr = q3 - q1                                             # Calcula el rango intercuartílico (IQR)
    lower = q1 - 1.5 * iqr                                    # Límite inferior para outliers
    upper = q3 + 1.5 * iqr                                    # Límite superior para outliers
    return series[(series < lower) | (series > upper)]        # Devuelve los valores fuera de los límites (posibles outliers)

def docs_to_dataframe(docs):                                  # Convierte una lista de documentos de Mongo a DataFrame con esquema uniforme
    if not docs:                                              # Si la lista está vacía
        return pd.DataFrame()                                 # Devuelve un DataFrame vacío
    df = pd.json_normalize(docs)                              # Aplana subdocumentos en columnas con notación punto
    rename_map = {                                            # Mapa de renombrado para columnas aplanadas
        "top_movie.title": "top_movie",
        "top_movie.gross": "top_movie_gross",
        "top_movie.inflation_adjusted_gross": "top_movie_inflation_adjusted_gross",
        "derived.gross_per_movie": "gross_per_movie",
        "derived.tickets_per_movie": "tickets_per_movie",
        "derived.decade": "decade"
    }
    df = df.rename(columns=rename_map)                        # Aplica el renombrado a las columnas
    expected_cols = ["genre", "year", "movies_released", "gross", "tickets_sold", "inflation_adjusted_gross",  # Lista de columnas esperadas
                     "top_movie", "top_movie_gross", "top_movie_inflation_adjusted_gross",
                     "gross_per_movie", "tickets_per_movie", "decade"]
    for c in expected_cols:                                   # Itera por cada columna esperada
        if c not in df.columns:                               # Si la columna no existe aún
            df[c] = pd.NA                                     # La crea con valores nulos
    num_cols = ["year", "movies_released", "gross", "tickets_sold", "inflation_adjusted_gross",              # Columnas que deben ser numéricas
                "top_movie_gross", "top_movie_inflation_adjusted_gross", "gross_per_movie", "tickets_per_movie"]
    for c in num_cols:                                        # Recorre columnas numéricas
        df[c] = pd.to_numeric(df[c], errors="coerce")         # Convierte a numérico, poniendo NaN en valores inválidos
    df["genre"] = df["genre"].astype(str).str.strip()         # Asegura tipo string en género y quita espacios alrededor
    df["top_movie"] = df["top_movie"].astype(str).str.strip() # Asegura tipo string en título de top_movie y quita espacios
    if df["decade"].isna().any():                             # Si falta la columna decade o tiene nulos
        df["decade"] = df["year"].apply(lambda y: f"{int(y)//10*10}s" if not pd.isna(y) else pd.NA)  # Calcula la década desde el año
    return df                                                 # Devuelve el DataFrame listo para análisis

def run_eda_from_mongo(coll, output_dir: Path):               # Ejecuta un EDA básico y genera gráficos/CSVs
    docs = list(coll.find({}))                                # Lee todos los documentos de la colección
    if not docs:                                              # Si no hay documentos
        print("No se encontraron documentos en la colección. Ejecuta primero el ETL.")  # Mensaje de aviso
        return                                                # Sale de la función
    df = docs_to_dataframe(docs)                              # Convierte los documentos a DataFrame con esquema
    output_dir.mkdir(parents=True, exist_ok=True)             # Crea el directorio de salida si no existe
    df.to_csv(output_dir / "mongo_genre_stats_raw.csv", index=False)  # Exporta un CSV con los datos planos

    numeric_cols = ["movies_released", "gross", "tickets_sold", "inflation_adjusted_gross",  # Define columnas numéricas para describir
                    "top_movie_gross", "top_movie_inflation_adjusted_gross", "gross_per_movie", "tickets_per_movie"]
    desc = df[numeric_cols].describe()                        # Calcula estadísticas descriptivas para estas columnas
    desc.to_csv(output_dir / "descriptive_stats.csv")         # Guarda las estadísticas a CSV
    print("Saved descriptive statistics.")                    # Mensaje de confirmación

    genre_gross = df.groupby("genre")["inflation_adjusted_gross"].sum().sort_values(ascending=False)  # Suma el gross ajustado por género y ordena
    genre_gross.head(10).to_csv(output_dir / "top_genres_by_inflation_adjusted_gross.csv")             # Guarda el top 10 a CSV
    plt.figure(figsize=(10,6))                                 # Crea figura para gráfico de barras
    sns.barplot(x=genre_gross.head(10).values, y=genre_gross.head(10).index, palette="viridis")  # Dibuja barras horizontales
    plt.title("Top 10 géneros por Gross ajustado por inflación (acumulado)")  # Título del gráfico
    plt.xlabel("Inflation-Adjusted Gross")                     # Etiqueta del eje X
    plt.tight_layout()                                         # Ajusta diseño para evitar recortes
    plt.savefig(output_dir / "top10_genres_inflation_adjusted_gross.png")  # Guarda el PNG
    plt.close()                                                # Cierra la figura para liberar memoria

    top5_genres = genre_gross.head(5).index.tolist()           # Toma los 5 géneros con más gross ajustado
    df_top5 = (df[df["genre"].isin(top5_genres)]               # Filtra el DataFrame para esos géneros
               .pivot_table(index="year", columns="genre", values="inflation_adjusted_gross", aggfunc="sum")  # Genera tabla pivote año x género
               .fillna(0))                                     # Rellena nulos con 0
    plt.figure(figsize=(12,6))                                 # Crea figura para serie temporal
    df_top5.plot(marker='o')                                   # Dibuja líneas con marcadores por género
    plt.title("Tendencia de Gross ajustado por inflación - Top 5 géneros")  # Título
    plt.xlabel("Año")                                          # Etiqueta eje X
    plt.ylabel("Inflation-Adjusted Gross")                     # Etiqueta eje Y
    plt.grid(True)                                             # Activa cuadrícula
    plt.tight_layout()                                         # Ajusta diseño
    plt.savefig(output_dir / "trend_top5_genres.png")          # Guarda PNG
    plt.close()                                                # Cierra figura

    counts = df["genre"].value_counts()                        # Cuenta observaciones por género
    genres_more_than_5 = counts[counts >= 5].index.tolist()    # Selecciona géneros con al menos 5 observaciones
    df_box = df[df["genre"].isin(genres_more_than_5)]          # Filtra el DataFrame a esos géneros
    plt.figure(figsize=(12,8))                                 # Crea figura para boxplot
    sns.boxplot(data=df_box, x="inflation_adjusted_gross", y="genre")  # Dibuja boxplot por género (muestra outliers como puntos)
    plt.title("Boxplot de Gross ajustado por género (géneros con >=5 observaciones)")  # Título
    plt.tight_layout()                                         # Ajusta diseño
    plt.savefig(output_dir / "boxplot_inflation_adjusted_gross_by_genre.png")  # Guarda PNG
    plt.close()                                                # Cierra figura

    try:                                                       # Intenta detectar outliers por IQR en toda la columna
        outliers = detect_outliers_iqr(df["inflation_adjusted_gross"].dropna())  # Obtiene los valores extremos usando IQR
        outliers_df = df[df["inflation_adjusted_gross"].isin(outliers)]          # Filtra filas que son outliers
        outliers_df.to_csv(output_dir / "outliers_inflation_adjusted_gross.csv", index=False)  # Exporta a CSV los registros outlier
    except Exception as e:                                      # Si ocurre un error
        print("Error detectando outliers:", e)                  # Se informa el error

    corr = df[["tickets_sold", "gross", "inflation_adjusted_gross"]].corr()  # Calcula matriz de correlación entre tres métricas
    corr.to_csv(output_dir / "correlation_matrix.csv")         # Exporta la matriz a CSV
    plt.figure(figsize=(6,5))                                  # Crea figura para heatmap
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm")  # Dibuja el heatmap con valores anotados
    plt.title("Correlation matrix")                            # Título
    plt.tight_layout()                                         # Ajusta diseño
    plt.savefig(output_dir / "correlation_matrix.png")         # Guarda PNG
    plt.close()                                                # Cierra figura

    plt.figure(figsize=(8,6))                                  # Crea figura para scatter
    sns.scatterplot(data=df, x="tickets_sold", y="inflation_adjusted_gross", hue="genre", legend=False, alpha=0.7)  # Dibuja dispersión coloreada por género
    plt.title("Tickets Sold vs Inflation-Adjusted Gross")      # Título
    plt.tight_layout()                                         # Ajusta diseño
    plt.savefig(output_dir / "tickets_vs_inflation_gross.png") # Guarda PNG
    plt.close()                                                # Cierra figura

    df.sort_values("inflation_adjusted_gross", ascending=False).head(50).to_csv(output_dir / "top50_by_inflation_adjusted_gross.csv", index=False)  # Exporta Top 50 por gross ajustado
    print("EDA completado. Outputs guardados en:", output_dir) # Mensaje final de EDA

# ---- Gráficos de calidad (nulos, outliers, anomalías)
def zscore_series(s: pd.Series):                               # Calcula el z-score de una serie (estandarización)
    s = s.astype(float)                                        # Asegura tipo float
    std = s.std(ddof=0)                                        # Calcula desviación estándar poblacional (ddof=0)
    if pd.isna(std) or std == 0:                               # Si es NaN o cero (serie constante)
        std = 1.0                                              # Evita división por cero asignando 1
    return (s - s.mean()) / std                                # Devuelve (x - media) / std

def bivariate_outlier_flag(df: pd.DataFrame, x_col: str, y_col: str, radius_thresh: float = 4.0):  # Marca outliers bivariados usando radio en espacio z
    zx = zscore_series(df[x_col])                              # Z-score de la variable X
    zy = zscore_series(df[y_col])                              # Z-score de la variable Y
    r = np.sqrt(zx**2 + zy**2)                                 # Radio euclidiano en el plano z (distancia al origen)
    return r > radius_thresh, r                                # Devuelve máscara booleana de outliers y el radio

def rolling_mad_anomalies(s: pd.Series, window: int = 5, k: float = 3.5):  # Detecta anomalías temporales con mediana móvil + MAD
    s = s.astype(float).sort_index()                           # Asegura float y orden por índice (año)
    med = s.rolling(window=window, min_periods=max(3, window//2), center=True).median()  # Calcula mediana móvil centrada
    mad = (s - med).abs().rolling(window=window, min_periods=max(3, window//2), center=True).median()  # Calcula MAD móvil
    mad = mad.replace(0, np.nan)                               # Reemplaza MAD cero por NaN para evitar división por cero
    score = (s - med).abs() / (1.4826 * mad)                   # Calcula score robusto (aprox. z-score basado en MAD)
    return score > k, score                                    # Devuelve bandera de anomalía y el score

def run_quality_anomaly_graphs(coll, output_dir: Path):        # Genera gráficos de nulos, outliers y anomalías
    docs = list(coll.find({}))                                 # Lee todos los documentos
    if not docs:                                               # Si no hay datos
        print("No se encontraron documentos en la colección. Ejecuta primero el ETL.")  # Mensaje
        return                                                 # Sale
    df = docs_to_dataframe(docs)                               # Convierte documentos a DataFrame
    output_dir.mkdir(parents=True, exist_ok=True)              # Asegura directorio de salida

    # Nulos por columna
    cols = ["genre","year","movies_released","gross","tickets_sold","inflation_adjusted_gross",  # Define columnas a auditar
            "top_movie","top_movie_gross","top_movie_inflation_adjusted_gross","gross_per_movie","tickets_per_movie","decade"]
    missing_counts = df[cols].isna().sum().sort_values(ascending=False)  # Cuenta nulos por columna y ordena
    plt.figure(figsize=(10,6))                                # Crea figura
    sns.barplot(x=missing_counts.values, y=missing_counts.index, palette="magma")  # Gráfico de barras de nulos
    plt.title("Nulos por columna")                            # Título
    plt.xlabel("Cantidad de nulos")                           # Etiqueta X
    plt.tight_layout()                                        # Ajuste de diseño
    plt.savefig(output_dir / "missing_by_column.png")         # Guarda PNG
    plt.close()                                               # Cierra figura

    # Patrón de nulos (muestra)
    sample_n = min(200, len(df))                              # Determina tamaño de muestra (máx. 200 filas)
    df_sample = df[cols].sample(sample_n, random_state=42) if len(df) > sample_n else df[cols]  # Toma muestra o todo si hay poco
    plt.figure(figsize=(12,6))                                # Crea figura
    sns.heatmap(df_sample.isna().astype(int), cmap="Reds", cbar=False)  # Heatmap donde 1=nulo, 0=no nulo
    plt.title("Patrón de nulos (1=nulo) - muestra")           # Título
    plt.xlabel("Columnas")                                     # Eje X
    plt.ylabel("Filas (muestra)")                              # Eje Y
    plt.tight_layout()                                         # Ajuste de diseño
    plt.savefig(output_dir / "missing_pattern_heatmap.png")    # Guarda PNG
    plt.close()                                                # Cierra figura

    # Outliers univariados: 4 boxplots
    metrics = ["inflation_adjusted_gross", "gross", "tickets_sold", "gross_per_movie"]  # Métricas a evaluar
    fig, axes = plt.subplots(2, 2, figsize=(14,10))             # Crea cuadrícula 2x2 de subgráficos
    axes = axes.ravel()                                         # Aplana la matriz de ejes para iterar fácilmente
    for i, m in enumerate(metrics):                             # Itera por cada métrica
        sns.boxplot(data=df, x=m, ax=axes[i], color="#6baed6")  # Dibuja boxplot para la métrica
        axes[i].set_title(f"Boxplot (posibles outliers) - {m}") # Define título del subgráfico
    plt.tight_layout()                                          # Ajusta diseño
    plt.savefig(output_dir / "boxplots_outliers_multi.png")     # Guarda PNG con los 4 boxplots
    plt.close()                                                 # Cierra figura

    # Conteo de outliers IQR por género
    iqr_out = detect_outliers_iqr(df["inflation_adjusted_gross"].dropna())  # Detecta valores outlier en gross ajustado
    df_iqr = df[df["inflation_adjusted_gross"].isin(iqr_out)]               # Filtra filas que son outliers
    if not df_iqr.empty:                                                    # Si hay outliers detectados
        counts_by_genre = df_iqr["genre"].value_counts()                    # Cuenta cuántos por género
        plt.figure(figsize=(10,6))                                          # Crea figura
        sns.barplot(x=counts_by_genre.values, y=counts_by_genre.index, palette="Reds")  # Dibuja barras
        plt.title("Conteo de outliers (IQR) por género - inflation_adjusted_gross")     # Título
        plt.xlabel("Cantidad de outliers")                                  # Etiqueta X
        plt.tight_layout()                                                  # Ajusta
        plt.savefig(output_dir / "outliers_iqr_by_genre.png")               # Guarda PNG
        plt.close()                                                         # Cierra

    # Outliers bivariados: gross vs tickets_sold
    df_pair = df[["gross","tickets_sold","genre"]].dropna()                # Toma columnas necesarias y elimina filas con nulos
    flag, radius = bivariate_outlier_flag(df_pair, "gross", "tickets_sold", radius_thresh=4.0)  # Marca outliers por radio en z
    df_pair = df_pair.assign(outlier=flag, radius=radius)                  # Añade columnas de bandera y radio al DataFrame
    plt.figure(figsize=(8,6))                                              # Crea figura
    sns.scatterplot(data=df_pair[~df_pair["outlier"]], x="tickets_sold", y="gross", color="steelblue", alpha=0.5, label="Normal")  # Puntos normales
    sns.scatterplot(data=df_pair[df_pair["outlier"]], x="tickets_sold", y="gross", color="crimson", alpha=0.8, label="Outlier")    # Puntos outlier
    plt.title("Outliers bivariados (gross vs tickets_sold) - z-radius>4")  # Título
    plt.legend()                                                           # Muestra leyenda
    plt.tight_layout()                                                     # Ajuste de diseño
    plt.savefig(output_dir / "outliers_scatter_gross_vs_tickets.png")      # Guarda PNG
    plt.close()                                                            # Cierra figura

    # Anomalías temporales para Top 3 géneros (rolling median + MAD)
    top3_genres = df.groupby("genre")["inflation_adjusted_gross"].sum().sort_values(ascending=False).head(3).index.tolist()  # Selecciona los 3 géneros con mayor gross total
    fig, axes = plt.subplots(len(top3_genres), 1, figsize=(12, 4*len(top3_genres)), sharex=True)  # Crea una fila por género, compartiendo eje X
    if len(top3_genres) == 1:                                              # Si solo hay un género (caso borde)
        axes = [axes]                                                       # Normaliza a lista para iterar
    for ax, g in zip(axes, top3_genres):                                   # Itera par a par (eje, género)
        dfg = df[df["genre"] == g].dropna(subset=["year","inflation_adjusted_gross"]).sort_values("year")  # Filtra filas del género con año y valor presentes
        dfg = dfg.set_index("year")                                         # Usa el año como índice temporal
        flags, score = rolling_mad_anomalies(dfg["inflation_adjusted_gross"], window=5, k=3.5)  # Detecta anomalías con mediana móvil y MAD
        ax.plot(dfg.index, dfg["inflation_adjusted_gross"], marker="o", label="Valor")          # Dibuja la serie temporal
        ax.scatter(dfg.index[flags.fillna(False)], dfg["inflation_adjusted_gross"][flags.fillna(False)], color="red", label="Anomalía", zorder=3)  # Marca las anomalías en rojo
        ax.set_title(f"Anomalías temporales (rolling median + MAD) - {g}")  # Título por género
        ax.set_ylabel("Inflation-Adjusted Gross")                            # Etiqueta eje Y
        ax.grid(True, alpha=0.3)                                             # Muestra cuadrícula suave
    axes[-1].set_xlabel("Año")                                              # Etiqueta eje X en el último subgráfico
    handles, labels = axes[0].get_legend_handles_labels()                   # Recupera leyendas desde el primer eje
    fig.legend(handles, labels, loc="upper right")                          # Coloca la leyenda global en la esquina superior derecha
    plt.tight_layout()                                                      # Ajusta diseño
    plt.savefig(output_dir / "anomalies_timeseries_top3.png")               # Guarda PNG
    plt.close()                                                             # Cierra figura

    print("Gráficos de calidad generados en:", output_dir)                  # Mensaje final de generación de gráficos

# ---- Opción combinada: EDA + Calidad
def run_full_eda_and_quality(coll, output_dir: Path):        # Ejecuta EDA base y gráficos de calidad en una sola llamada
    run_eda_from_mongo(coll, output_dir)                     # Llama al EDA base (tablas y gráficos principales)
    run_quality_anomaly_graphs(coll, output_dir)             # Llama a los gráficos de nulos, outliers y anomalías

# ---------------------------
# Menú interactivo (10 opciones)
# ---------------------------
def print_menu():                                            # Imprime el menú de opciones en consola
    print("""                                                # Inicia un string multilínea para mostrar el menú
Elige una opción:
 1) Suma acumulada de Gross ajustado por género
 2) Años con más películas lanzadas (Top N)
 3) Top títulos que aparecieron como 'top_movie' (Top N)
 4) Géneros con mayor crecimiento entre dos años (start,end)
 5) Años con más blockbusters (top_movie.gross >= umbral)
 6) Buckets automáticos sobre inflation_adjusted_gross
 7) Mostrar registros de ejemplo para un género
 8) Serie temporal de movies_released para géneros (top o especificados)
 9) Estadísticas de revenue per ticket por género
10) EDA completo + Gráficos de calidad (outliers, nulos y anomalías)
 0) Salir
""")                                                        # Cierra el print del menú

def main():                                                  # Función principal del script
    parser = argparse.ArgumentParser()                       # Crea un parser de argumentos CLI
    parser.add_argument("--mongo-uri", default=os.environ.get("MONGO_URI", DEFAULT_MONGO_URI))  # Argumento: URI de Mongo (lee ENV o usa default)
    parser.add_argument("--db", default="etl_lab")           # Argumento: nombre de base de datos (default etl_lab)
    parser.add_argument("--collection", default="genre_stats")  # Argumento: nombre de colección (default genre_stats)
    parser.add_argument("--output-dir", default="outputs")   # Argumento: carpeta de salida para archivos generados
    args = parser.parse_args()                               # Parsea los argumentos recibidos

    out_dir = Path(args.output_dir)                          # Convierte la ruta de salida a objeto Path
    try:                                                     # Intenta establecer conexión con Mongo
        client = MongoClient(args.mongo_uri)                 # Crea cliente de MongoDB con la URI indicada
        coll = client[args.db][args.collection]              # Obtiene la colección a trabajar
        _ = coll.estimated_document_count()                  # Realiza una operación simple para verificar conectividad
    except Exception as e:                                    # Si ocurre error de conexión
        print("Error conectando a MongoDB:", e)              # Imprime el error
        sys.exit(1)                                          # Sale del programa con código de error 1

    actions = {                                              # Mapa de opciones del menú a funciones ejecutables
        "1": (lambda: total_inflation_adjusted_gross_per_genre(coll)),  # Opción 1: totales por género
        "2": (lambda: top_years_by_movies_released(coll, top_n=int(input("Top N (default 10): ") or "10"))),  # Opción 2: top años por películas lanzadas
        "3": (lambda: top_movies_overall(coll, top_n=int(input("Top N (default 10): ") or "10"))),            # Opción 3: top títulos como top_movie
        "4": (lambda: genres_with_highest_growth(coll,                                                     # Opción 4: crecimiento por género
                                                start_year=int(input("Año inicial (ej. 1995): ") or "1995"),
                                                end_year=int(input("Año final (ej. 2018): ") or "2018"),
                                                top_n=int(input("Top N (default 10): ") or "10"))),
        "5": (lambda: years_with_most_blockbusters(coll, threshold=float(input("Umbral gross (ej. 300000000): ") or "300000000"))),  # Opción 5: años con más blockbusters
        "6": (lambda: bucket_movies_by_gross(coll, buckets=int(input("Número de buckets (ej. 5): ") or "5"))),                        # Opción 6: buckets automáticos
        "7": (lambda: sample_records_for_genre(coll, genre=input("Género (ej. Action): ").strip(), limit=int(input("Límite (ej. 20): ") or "20"))),  # Opción 7: muestra por género
        "8": (lambda: genres_movies_released_trend(coll, genre_list=[g.strip() for g in input("Géneros separados por coma (enter = top5): ").split(",")] if input("¿Quieres ingresar géneros manualmente? (s/n): ").lower() == "s" else None)),  # Opción 8: serie temporal
        "9": (lambda: revenue_per_ticket_stats(coll)),                                                                                 # Opción 9: revenue per ticket por género
        "10": (lambda: run_full_eda_and_quality(coll, out_dir))                                                                        # Opción 10: EDA + calidad
    }

    try:                                                     # Bucle principal del menú con control de interrupción
        while True:                                          # Inicia un ciclo infinito hasta que el usuario elija salir
            print_menu()                                     # Muestra el menú
            choice = input("Opción: ").strip()               # Lee la opción del usuario y elimina espacios
            if choice == "0":                                # Si la opción es 0
                print("Saliendo.")                           # Informa que saldrá
                break                                        # Rompe el bucle y termina
            if choice not in actions:                        # Si la opción no está en el mapa de acciones
                print("Opción inválida.")                    # Informa opción inválida
                continue                                     # Vuelve al inicio del bucle
            print(f"Ejecutando opción {choice}...")          # Informa la opción que ejecutará
            result = actions[choice]()                       # Ejecuta la función asociada a la opción y captura el resultado
            # La opción 10 genera archivos y no retorna lista de resultados
            if choice == "10":                               # Si la opción fue la 10 (EDA+calidad)
                continue                                     # No intenta imprimir CSV/resultado tabular
            if isinstance(result, list):                     # Si el resultado es una lista (típicamente de agregación)
                pprint(result[:50])                          # Imprime una muestra de hasta 50 elementos de forma legible
                fname = out_dir / f"query_{choice}.csv"      # Construye el nombre del CSV de salida
                out_dir.mkdir(parents=True, exist_ok=True)   # Asegura que el directorio de salida exista
                try:                                         # Intenta guardar a CSV
                    df = pd.DataFrame(result)                # Convierte la lista de resultados en DataFrame
                    df.to_csv(fname, index=False)            # Escribe el CSV sin índice
                    print(f"Resultados guardados en: {fname}")  # Informa ruta guardada
                except Exception as e:                        # Si ocurre error al guardar
                    print("No se pudieron guardar los resultados a CSV:", e)  # Muestra el error
            else:                                            # Si el resultado no es lista (puede ser dict u otro)
                pprint(result)                               # Imprime el resultado tal cual
    except KeyboardInterrupt:                                 # Captura Ctrl+C del usuario
        print("\nInterrupción por usuario.")                  # Mensaje de interrupción
    finally:                                                  # Bloque que se ejecuta siempre al final
        try:                                                  # Intenta cerrar el cliente de Mongo
            client.close()                                    # Cierra la conexión a MongoDB
        except:                                               # Si falla el cierre (poco probable)
            pass                                              # Ignora silenciosamente

if __name__ == "__main__":                                    # Punto de entrada cuando el script se ejecuta directamente
    main()                                                    # Llama a la función principal