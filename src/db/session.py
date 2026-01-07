from sqlmodel import SQLModel, Session, create_engine
from src.utils.config import settings

# IMPORTANTE: Importe os modelos aqui para registrá-los no SQLModel
from src.models.deck import Deck
from src.models.flashcard import Flashcard
from src.models.usage_log import UsageLog

engine = create_engine(
    settings.DATABASE_URL, 
    connect_args={"check_same_thread": False}, 
    echo=False
)

def init_db():
    # Agora o create_all "enxerga" Deck e Flashcard
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session