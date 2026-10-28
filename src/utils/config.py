import os
from pathlib import Path
from dotenv import load_dotenv

# Tim file .env tu thu muc goc du an
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()


class Settings:
    # OpenAQ API
    OPENAQ_API_KEY: str = os.getenv("OPENAQ_API_KEY", "")
    OPENAQ_BASE_URL: str = os.getenv("OPENAQ_BASE_URL", "https://api.openaq.org/v3")
    TARGET_COUNTRY_ISO: str = os.getenv("TARGET_COUNTRY_ISO", "VN")
    DEFAULT_LIMIT: int = int(os.getenv("DEFAULT_LIMIT", "100"))
    OPENAQ_ALLOW_MOCK: bool = os.getenv("OPENAQ_ALLOW_MOCK", "False").lower() in ("true", "1", "yes")
    CITIES_CONFIG_PATH: Path = BASE_DIR / "config" / "cities.yaml"

    # S3 / MinIO
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
    S3_ACCESS_KEY: str = os.getenv("S3_ACCESS_KEY", "minioadmin")
    S3_SECRET_KEY: str = os.getenv("S3_SECRET_KEY", "minioadmin")
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "openaq-data-lake")
    S3_REGION: str = os.getenv("S3_REGION", "us-east-1")
    S3_USE_SSL: bool = os.getenv("S3_USE_SSL", "False").lower() in ("true", "1", "yes")

    # Data Warehouse PostgreSQL
    DWH_DB_HOST: str = os.getenv("DWH_DB_HOST", "localhost")
    DWH_DB_PORT: int = int(os.getenv("DWH_DB_PORT", "5432"))
    DWH_DB_NAME: str = os.getenv("DWH_DB_NAME", "openaq_dw")
    DWH_DB_USER: str = os.getenv("DWH_DB_USER", "postgres")
    DWH_DB_PASSWORD: str = os.getenv("DWH_DB_PASSWORD", "postgres")
    DWH_DB_SCHEMA: str = os.getenv("DWH_DB_SCHEMA", "public")

    @property
    def sqlalchemy_db_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.DWH_DB_USER}:{self.DWH_DB_PASSWORD}"
            f"@{self.DWH_DB_HOST}:{self.DWH_DB_PORT}/{self.DWH_DB_NAME}"
        )


settings = Settings()
