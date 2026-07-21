from fastapi import FastAPI

app = FastAPI(title="RAG Atas UFES")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
