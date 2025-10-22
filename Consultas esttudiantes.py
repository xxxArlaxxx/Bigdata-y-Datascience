
import pprint
from pymongo import MongoClient
MONGODB_URI = "mongodb+srv://Test:WK3VITtncqnnjQrr@cluster0.mjng6tk.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGODB_URI)
db = client['etl_lab']
collection = db['students']
pp = pprint.PrettyPrinter(indent=2, width=100)
def consulta_horas_estudio_rango():
    try:
        minimo = float(input("Horas de estudio mínimas: "))
        maximo = float(input("Horas de estudio máximas: "))
    except ValueError:
        print("Valores inválidos.")
        return
    q = {"hours_studied": {"$gte": minimo, "$lte": maximo}}
    for doc in collection.find(q).limit(100):
        pp.pprint(doc)

def consulta_exam_mayor():
    try:
        minimo = float(input("Exam score mínimo: "))
    except ValueError:
        print("Valor inválido.")
        return
    q = {"exam_score": {"$gte": minimo}}
    for doc in collection.find(q).sort("exam_score", -1).limit(100):
        pp.pprint(doc)

def consulta_asistencia_rango():
    try:
        minimo = float(input("Asistencia mínima (%): "))
        maximo = float(input("Asistencia máxima (%): "))
    except ValueError:
        print("Valores inválidos.")
        return
    q = {"attendance_percent": {"$gte": minimo, "$lte": maximo}}
    for doc in collection.find(q).limit(100):
        pp.pprint(doc)

def consulta_previous_mayor():
    try:
        minimo = float(input("Previous score mínimo: "))
    except ValueError:
        print("Valor inválido.")
        return
    q = {"previous_scores": {"$gte": minimo}}
    for doc in collection.find(q).sort("previous_scores", -1).limit(100):
        pp.pprint(doc)

def consulta_sleep_rango():
    try:
        minimo = float(input("Horas de sueño mínimas: "))
        maximo = float(input("Horas de sueño máximas: "))
    except ValueError:
        print("Valores inválidos.")
        return
    q = {"sleep_hours": {"$gte": minimo, "$lte": maximo}}
    for doc in collection.find(q).limit(100):
        pp.pprint(doc)

def consulta_count_por_buckets_hours():
    # Cuenta estudiantes por buckets automáticos de hours_studied
    pipeline = [
        {"$bucketAuto": {"groupBy": "$hours_studied", "buckets": 5}},
        {"$project": {"_id": 0, "min": "$min", "max": "$max", "count": "$count"}}
    ]
    for doc in collection.aggregate(pipeline):
        pp.pprint(doc)

def consulta_top_n_exam():
    try:
        n = int(input("¿Cuántos estudiantes (Top N por exam_score)?: "))
    except ValueError:
        print("Valor inválido.")
        return
    for doc in collection.find({}).sort("exam_score", -1).limit(n):
        pp.pprint(doc)

def consulta_student_id_contiene():
    texto = input("Texto a buscar en student_id: ").strip()
    if not texto:
        print("Texto vacío.")
        return
    q = {"student_id": {"$regex": texto, "$options": "i"}}
    for doc in collection.find(q).limit(100):
        pp.pprint(doc)

def consulta_promedio_rango():
    try:
        minimo = float(input("Promedio general mínimo: "))
        maximo = float(input("Promedio general máximo: "))
    except ValueError:
        print("Valores inválidos.")
        return
    q = {"promedio_general": {"$gte": minimo, "$lte": maximo}}
    for doc in collection.find(q).limit(100):
        pp.pprint(doc)

def consulta_estadisticas_exam():
    pipeline = [
        {
            "$group": {
                "_id": None,
                "count": {"$sum": 1},
                "min": {"$min": "$exam_score"},
                "max": {"$max": "$exam_score"},
                "avg": {"$avg": "$exam_score"},
                "stdDev": {"$stdDevSamp": "$exam_score"}
            }
        },
        {"$project": {"_id": 0}}
    ]
    for doc in collection.aggregate(pipeline):
        pp.pprint(doc)

menu = """
Elige una consulta:
1. Estudiantes por rango de horas de estudio
2. Estudiantes con exam_score mayor o igual a X
3. Estudiantes por rango de asistencia (%)
4. Estudiantes con previous_scores >= X
5. Estudiantes por rango de horas de sueño
6. Conteo por buckets de hours_studied
7. Top N por exam_score
8. Buscar por texto en student_id
9. Estudiantes por rango de promedio_general
10. Estadísticas de exam_score (count, min, max, avg, stdDev)
0. Salir
"""

acciones = {
    "1": consulta_horas_estudio_rango,
    "2": consulta_exam_mayor,
    "3": consulta_asistencia_rango,
    "4": consulta_previous_mayor,
    "5": consulta_sleep_rango,
    "6": consulta_count_por_buckets_hours,
    "7": consulta_top_n_exam,
    "8": consulta_student_id_contiene,
    "9": consulta_promedio_rango,
    "10": consulta_estadisticas_exam
}

if __name__ == "__main__":
    while True:
        print(menu)
        opcion = input("Opción: ").strip()
        if opcion == "0":
            print("¡Hasta luego!")
            break
        accion = acciones.get(opcion)
        if accion:
            try:
                accion()
            except Exception as e:
                print(f"Error al ejecutar la consulta: {e}")
        else:
            print("Opción inválida, intenta de nuevo.")