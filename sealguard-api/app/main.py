from fastapi import FastAPI

from app.api.routes import router as api_router

app = FastAPI(title="SealGuard API", version="0.1.0")
app.include_router(api_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "sealguard-api", "message": "running"}
