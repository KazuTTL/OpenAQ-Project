import psycopg2
from psycopg2.extras import execute_values
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from src.utils.config import settings
from src.utils.logger import get_logger

logger = get_logger("DBConnector")


class DBConnector:
    _engine: Engine = None

    @classmethod
    def get_engine(cls) -> Engine:
        if cls._engine is None:
            logger.info("Khoi tao SQLAlchemy Engine ket noi toi PostgreSQL DWH")
            cls._engine = create_engine(
                settings.sqlalchemy_db_url,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
            )
        return cls._engine

    @classmethod
    def get_raw_connection(cls):
        return psycopg2.connect(
            host=settings.DWH_DB_HOST,
            port=settings.DWH_DB_PORT,
            dbname=settings.DWH_DB_NAME,
            user=settings.DWH_DB_USER,
            password=settings.DWH_DB_PASSWORD,
        )

    @classmethod
    def execute_script(cls, sql_script: str) -> None:
        conn = cls.get_raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql_script)
            conn.commit()
            logger.info("Thuc thi tap lenh SQL thanh cong.")
        except Exception as e:
            conn.rollback()
            logger.error(f"Loi thuc thi SQL: {e}")
            raise
        finally:
            conn.close()
