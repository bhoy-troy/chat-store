from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ollama_url: str = "http://ollama:11434"
    embed_model: str = "nomic-embed-text"
    chat_model: str = "llama3.1"
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "confluence"
    top_k: int = 6
    max_context_chars: int = 12000
    ingest_interval_minutes: int = 10

    class Config:
        env_file = ".env"


settings = Settings()
