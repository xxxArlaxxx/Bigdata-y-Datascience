# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
rng = np.random.default_rng(42)
def clip(a, lo, hi):
    return np.clip(a, lo, hi)

student_ids = [f"S{str(i).zfill(3 if N < 1000 else 4)}" for i in range(1, N + 1)]
hours_studied = clip(rng.normal(6.5, 3.0, N), 0, 12)
sleep_hours = clip(rng.normal(7.0, 1.5, N), 3, 10)
attendance_percent = clip(rng.normal(75, 12, N), 50, 100)
previous_scores = clip(rng.normal(70, 12, N), 40, 95).round().astype(int)

noise = rng.normal(0, 4.0, N)
exam_score = (
    0.45 * previous_scores.astype(float) +
    0.25 * (hours_studied * 4.0) +
    0.20 * (attendance_percent / 3.0) +
    noise
)
exam_score = clip(exam_score, 0, 100)
promedio_general = (previous_scores.astype(float) + exam_score.astype(float)) / 2.0

df = pd.DataFrame({
    "student_id": student_ids,
    "hours_studied": hours_studied.round(1),
    "sleep_hours": sleep_hours.round(1),
    "attendance_percent": attendance_percent.round(1),
    "previous_scores": previous_scores,
    "exam_score": exam_score.round(1),
    "promedio general": promedio_general.round(1)
})
df.to_csv("student_exam_scores.csv", index=False)
print(f"Dataset sintético generado en student_exam_scores.csv con {N} filas e incluye la columna 'promedio general'.")