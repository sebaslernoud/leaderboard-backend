from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import asyncio
import httpx
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

async def fetch_user_from_api(username: str):
    async with httpx.AsyncClient() as client:
        # JSONPlaceholder devuelve un array, filtramos por username
        response = await client.get(f"https://jsonplaceholder.typicode.com/users?username={username}")
        data = response.json()
        if data and len(data) > 0:
            return data[0] # Devolvemos el primer usuario que coincida
        return None


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




# ==========================================
# ENDPOINT 1: LA API LENTA (Sin Caché)
# ==========================================
@app.get("/api/slow-data/{username}")
async def get_slow_data(username: str):
    await asyncio.sleep(5) 
    
    user_data = await fetch_user_from_api(username)
    
    if not user_data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado en la API externa")
    
    user_data["source"] = "🐢 API Externa (Lento y sin caché)"
    return user_data


@app.get("/api/fast-data/{username}")
async def get_fast_data(username: str):
    if not r:
        raise HTTPException(status_code=500, detail="Redis no configurado")
        
    cache_key = f"user_profile:{username}"
    
    # 1. INTENTO DE LECTURA EN REDIS (Caché Hit)
    cached_data = r.get(cache_key)
    
    if cached_data:
        # ¡Está en Redis! Respondemos al instante (0 segundos de espera)
        response = json.loads(cached_data)
        response["source"] = "⚡ Recuperado desde Redis (Caché Hit)"
        return response
        
    # 2. LECTURA LENTA (Caché Miss)
    # Si no está en Redis, sufrimos la penalización de los 5 segundos simulados
    await asyncio.sleep(5)
    
    user_data = await fetch_user_from_api(username)
    
    if not user_data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado en la API externa")
    
    user_data["source"] = "🐢 API Externa (Caché Miss - Guardando en Redis...)"
    
    # 3. GUARDAR EN CACHÉ
    # Lo guardamos como String (JSON) por 60 segundos
    r.setex(cache_key, 60, json.dumps(user_data))
    
    return user_data