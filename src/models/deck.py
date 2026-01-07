from typing import List, Optional
from sqlmodel import SQLModel, Field, Relationship

class Deck(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    topic: str
    language: str 
    is_public: bool = Field(default=False)
    
    cards: List["Flashcard"] = Relationship(back_populates="deck")  