from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"message": "pong"}
