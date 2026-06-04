from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis
import time
import os

app = FastAPI()

# Permitir que tus alumnos se conecten desde sus entornos locales de React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Conexión a Redis usando una Variable de Entorno que configuraremos en Vercel
REDIS_URL = os.getenv("REDIS_URL")
r = redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None

class Student(BaseModel):
    name: str

@app.get("/api/health")
def health_check():
    return {"status": "ok", "redis_connected": r is not None}

@app.post("/api/submit")
def submit_name(student: Student):
    if not r:
        raise HTTPException(status_code=500, detail="Redis no configurado")
    
    name = student.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    
    # Usamos timestamp en milisegundos como score para el Sorted Set
    timestamp = time.time() * 1000
    
    # Guardamos en el sorted set llamado 'leaderboard'
    r.zadd("leaderboard", {name: timestamp})
    return {"status": "success", "message": f"¡{name} registrado!"}

@app.get("/api/leaderboard")
def get_leaderboard():
    if not r:
        return {"leaderboard": []}
    
    # Trae todos los alumnos ordenados del menor timestamp (primero) al mayor
    data = r.zrange("leaderboard", 0, -1, withscores=True)
    
    # Formateamos la respuesta para el frontend
    leaderboard = [{"name": name, "timestamp": score} for name, score in data]
    return {"leaderboard": leaderboard}