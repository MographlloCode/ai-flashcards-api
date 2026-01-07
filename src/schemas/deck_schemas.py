from pydantic import BaseModel
from typing import List, Optional
from src.schemas.flashcard_schemas import FlashcardResponse

# Input
class GenerateDeckRequest(BaseModel):
    topic: str
    language: str = "pt-br"

# Novo Schema intermediário: Um Nível contendo vários cards
class DeckLevelResponse(BaseModel):
    level: str
    cards: List[FlashcardResponse]

# Output Final Estruturado
class GeneratedDeckResponse(BaseModel):
    topic: str # O tópico limpo (ex: "System Design")
    original_input: Optional[str] = None # O que o user digitou (ex: "Quero aprender System Design")
    language: str
    total_cards: int
    cards: List[DeckLevelResponse]