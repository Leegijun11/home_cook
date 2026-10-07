from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str
    openai_model: str = "gpt-5-mini"
    embedding_model: str = "text-embedding-3-small"
    critic_score_threshold: float = 6.0

    class Config:
        env_file = ".env"


settings = Settings()
