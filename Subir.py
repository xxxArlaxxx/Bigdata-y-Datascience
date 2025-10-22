import pandas as pd
from pymongo import MongoClient
MONGODB_URI = "mongodb+srv://Test:WK3VITtncqnnjQrr@cluster0.mjng6tk.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGODB_URI)
db = client['etl_lab']
collection = db['students']

df = pd.read_csv('student_exam_scores.csv')
num_cols = ["hours_studied", "sleep_hours", "attendance_percent", "previous_scores", "exam_score"]
for c in num_cols:
    df[c] = pd.to_numeric(df[c], errors="coerce")

for c in num_cols:
    if df[c].isna().any():
        df[c] = df[c].fillna(df[c].median())
df["promedio_general"] = (df["previous_scores"].astype(float) + df["exam_score"].astype(float)) / 2.0
for _, row in df.iterrows():
    doc = {
        "student_id": str(row["student_id"]),
        "hours_studied": float(row["hours_studied"]),
        "sleep_hours": float(row["sleep_hours"]),
        "attendance_percent": float(row["attendance_percent"]),
        "previous_scores": int(row["previous_scores"]),
        "exam_score": float(row["exam_score"]),
        "promedio_general": float(row["promedio_general"])
    }
    collection.insert_one(doc)
    print(f'Estudiante {doc["student_id"]} subido a MongoDB Atlas')

print("Catálogo de estudiantes subido exitosamente a MongoDB Atlas.")