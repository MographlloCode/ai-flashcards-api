from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field

class UsageLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Qual modelo foi usado (ex: llama-3.3-70b)
    model_id: str 
    
    # Métricas da Groq
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    
    # Tempo que levou (opcional, bom para debug de latência)
    time_taken_seconds: float = 0.0
    
    # Contexto (ex: "architect", "builder-iniciante")
    context_tag: str