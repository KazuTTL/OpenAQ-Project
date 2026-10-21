import io
import json
import boto3
from botocore.exceptions import ClientError
import pandas as pd
from typing import Any, Dict, List, Optional
from src.utils.config import settings
from src.utils.logger import get_logger

logger = get_logger("S3Writer")


class S3Writer:
    def __init__(self):
        self.bucket_name = settings.S3_BUCKET_NAME
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            use_ssl=settings.S3_USE_SSL,
        )
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self) -> None:
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError:
            try:
                logger.info(f"Bucket {self.bucket_name} chua ton tai, dang tao moi...")
                self.s3_client.create_bucket(Bucket=self.bucket_name)
                logger.info(f"Tao bucket {self.bucket_name} thanh cong.")
            except Exception as e:
                logger.warning(f"Khong the kiem tra hoac tao bucket: {e}")

    def upload_raw_json(self, data: Any, s3_key: str) -> str:
        try:
            payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=payload,
                ContentType="application/json",
            )
            logger.info(f"Da tai len S3 thanh cong: s3://{self.bucket_name}/{s3_key}")
            return f"s3://{self.bucket_name}/{s3_key}"
        except Exception as e:
            logger.error(f"Loi khi tai JSON len S3 ({s3_key}): {e}")
            raise

    def read_raw_json(self, s3_key: str) -> Any:
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            content = response["Body"].read().decode("utf-8")
            return json.loads(content)
        except Exception as e:
            logger.error(f"Loi khi doc JSON tu S3 ({s3_key}): {e}")
            raise

    def upload_parquet(self, df: pd.DataFrame, s3_key: str) -> str:
        try:
            buffer = io.BytesIO()
            df.to_parquet(buffer, index=False, engine="pyarrow")
            buffer.seek(0)
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=buffer.getvalue(),
                ContentType="application/octet-stream",
            )
            logger.info(f"Da ghi DataFrame Parquet len S3: s3://{self.bucket_name}/{s3_key} ({len(df)} rows)")
            return f"s3://{self.bucket_name}/{s3_key}"
        except Exception as e:
            logger.error(f"Loi khi ghi Parquet len S3 ({s3_key}): {e}")
            raise

    def read_parquet(self, s3_key: str) -> pd.DataFrame:
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            buffer = io.BytesIO(response["Body"].read())
            df = pd.read_parquet(buffer, engine="pyarrow")
            return df
        except Exception as e:
            logger.error(f"Loi khi doc Parquet tu S3 ({s3_key}): {e}")
            raise

    def list_keys(self, prefix: str) -> List[str]:
        try:
            paginator = self.s3_client.get_paginator("list_objects_v2")
            keys = []
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"])
            return keys
        except Exception as e:
            logger.error(f"Loi khi liet ke danh sach file tai S3 prefix {prefix}: {e}")
            return []
