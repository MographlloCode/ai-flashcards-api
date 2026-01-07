from typing import List, Optional, Dict
from sqlmodel import SQLModel, Field, Relationship

class Flashcard(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    front: str
    back: str
    
    generated_by_model: Optional[str] = None
    quality_flag: str = "ok" # "ok" ou "needs_review" (flag amarela)
    
    deck_id: Optional[int] = Field(default=None, foreign_key="deck.id")
    deck: Optional["Deck"] = Relationship(back_populates="cards")    