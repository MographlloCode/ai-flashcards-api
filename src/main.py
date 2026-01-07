from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.db.session import init_db
from src.schemas.deck_schemas import GenerateDeckRequest, GeneratedDeckResponse
from src.services.ai_orchestrator import generate_full_deck_service
from src.services.usage_service import get_daily_usage_stats
import os, requests

# Evento para criar tabelas ao iniciar
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/")
def read_root():
    return {"status": "AI Flashcards API is running 🚀"}

@app.post("/api/generate", response_model=GeneratedDeckResponse)
async def generate_deck(request: GenerateDeckRequest):
    # Passamos o request.language agora
    result = await generate_full_deck_service(request.topic, request.language)
    return result
  
@app.get('/models')
def get_groq_models():
  api_key = os.environ.get("GROQ_API_KEY")
  url = "https://api.groq.com/openai/v1/models"

  headers = {
      "Authorization": f"Bearer {api_key}",
      "Content-Type": "application/json"
  }

  response = requests.get(url, headers=headers)
  return response.json()

@app.get("/api/usage")
def read_usage():
    """
    Retorna o consumo de tokens e requisições do dia atual (Free Tier Stats).
    """
    return get_daily_usage_stats()