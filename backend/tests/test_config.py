from app.core.config import Settings


def test_database_url_built_from_env(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "foo")
    monkeypatch.setenv("POSTGRES_PASSWORD", "bar")
    monkeypatch.setenv("POSTGRES_DB", "baz")
    monkeypatch.setenv("POSTGRES_HOST", "db-host")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")

    settings = Settings()

    assert settings.database_url == "postgresql+psycopg2://foo:bar@db-host:5432/baz"


def test_neo4j_uri_built_from_env(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "foo")
    monkeypatch.setenv("POSTGRES_PASSWORD", "bar")
    monkeypatch.setenv("POSTGRES_DB", "baz")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("NEO4J_HOST", "graph-host")
    monkeypatch.setenv("NEO4J_BOLT_PORT", "7688")

    settings = Settings()

    assert settings.neo4j_uri == "bolt://graph-host:7688"


def test_qdrant_url_built_from_env(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "foo")
    monkeypatch.setenv("POSTGRES_PASSWORD", "bar")
    monkeypatch.setenv("POSTGRES_DB", "baz")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("QDRANT_HOST", "vector-host")
    monkeypatch.setenv("QDRANT_HTTP_PORT", "6334")

    settings = Settings()

    assert settings.qdrant_url == "http://vector-host:6334"


def test_ollama_base_url_built_from_env(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "foo")
    monkeypatch.setenv("POSTGRES_PASSWORD", "bar")
    monkeypatch.setenv("POSTGRES_DB", "baz")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("OLLAMA_HOST", "llm-host")
    monkeypatch.setenv("OLLAMA_PORT", "11435")

    settings = Settings()

    assert settings.ollama_base_url == "http://llm-host:11435"
