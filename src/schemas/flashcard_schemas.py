from pydantic import BaseModel
from typing import Optional

# O card que devolvemos para o Frontend (Output)
class FlashcardResponse(BaseModel):
    front: str
    back: str
    generated_by_model: Optional[str] = None
    quality_flag: str