from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_user: str
    postgres_password: SecretStr
    postgres_db: str
    postgres_host: str = "localhost"
    postgres_port: int = 5433

    neo4j_user: str
    neo4j_password: SecretStr
    neo4j_host: str = "localhost"
    neo4j_bolt_port: int = 7687

    qdrant_host: str = "localhost"
    qdrant_http_port: int = 6333

    ollama_host: str = "localhost"
    ollama_port: int = 11434

    llm_provedor: str = "ollama"
    llm_modelo: str = "qwen2.5:7b"
    llm_timeout: float = 120.0
    llm_max_tokens: int = 4096
    llm_num_ctx: int = 16384
    anthropic_api_key: SecretStr | None = None

    anonymization_secret_key: SecretStr
    atas_corpus_path: Path

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password.get_secret_value()}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def neo4j_uri(self) -> str:
        return f"bolt://{self.neo4j_host}:{self.neo4j_bolt_port}"

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_http_port}"

    @property
    def ollama_base_url(self) -> str:
        return f"http://{self.ollama_host}:{self.ollama_port}"


settings = Settings()
