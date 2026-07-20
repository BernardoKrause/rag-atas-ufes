from app.core.config import settings


def test_database_url_built_from_env():
    assert settings.database_url == (
        "postgresql+psycopg2://rag_atas_ufes:changeme@localhost:5433/rag_atas_ufes"
    )


def test_neo4j_uri_built_from_env():
    assert settings.neo4j_uri == "bolt://localhost:7687"


def test_qdrant_url_built_from_env():
    assert settings.qdrant_url == "http://localhost:6333"


def test_ollama_base_url_built_from_env():
    assert settings.ollama_base_url == "http://localhost:11434"
