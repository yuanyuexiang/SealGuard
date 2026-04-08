from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@dataclass(frozen=True)
class Settings:
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    database_url: str
    sealvision_bundle_dir: str
    sealvision_img_size: int
    sealvision_conf: float
    sealvision_device: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    db = os.getenv("POSTGRES_DB", "sealguard")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "123456")

    default_db_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"

    project_root = Path(__file__).resolve().parents[1]
    default_bundle_dir = project_root.parent / "sealguard-ai" / "sealvision_model_bundle_20260408"

    return Settings(
        postgres_host=host,
        postgres_port=port,
        postgres_db=db,
        postgres_user=user,
        postgres_password=password,
        database_url=os.getenv("DATABASE_URL", default_db_url),
        sealvision_bundle_dir=os.getenv("SEALVISION_BUNDLE_DIR", str(default_bundle_dir)),
        sealvision_img_size=int(os.getenv("SEALVISION_IMG_SIZE", "960")),
        sealvision_conf=float(os.getenv("SEALVISION_CONF", "0.25")),
        sealvision_device=os.getenv("SEALVISION_DEVICE", "cpu"),
    )
