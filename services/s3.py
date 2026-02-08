import os
import logging
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, InvalidRegionError, ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class S3Client:
    """
    Lightweight S3 client with runtime validation.
    Can be safely instantiated in DEV even without credentials.
    """

    def __init__(self):
        self.bucket = os.getenv("S3_BUCKET")
        self.access_key = os.getenv("AWS_ACCESS_KEY_ID")
        self.secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.region = os.getenv("AWS_REGION")
        self.client = None

        if not all([self.bucket, self.access_key, self.secret_key, self.region]):
            logger.warning(
                "AWS S3 credentials or bucket missing. "
                "S3Client will fail on runtime calls until environment variables are set."
            )
        else:
            self._init_client()

    def _init_client(self):
        """Initialize boto3 client."""
        try:
            self.client = boto3.client(
                "s3",
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region
            )
            logger.info(f"S3 client initialized for bucket: {self.bucket}, region: {self.region}")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            raise

    def download_file(self, key: str, local_path: str):
        """Download a file from S3 to a local path."""
        if not self.client:
            self._init_client()
        try:
            logger.info(f"Downloading S3 file: {key} -> {local_path}")
            self.client.download_file(self.bucket, key, local_path)
            logger.info(f"Download successful: {local_path}")
        except (NoCredentialsError, PartialCredentialsError) as cred_err:
            logger.error(f"AWS credentials error: {cred_err}")
            raise
        except ClientError as client_err:
            logger.error(f"S3 client error: {client_err}")
            raise
        except Exception as e:
            logger.error(f"Unexpected S3 download error: {e}")
            raise

    def upload_file(self, local_path: str, key: str):
        """Upload a local file to S3."""
        if not self.client:
            self._init_client()
        try:
            logger.info(f"Uploading {local_path} -> S3:{key}")
            self.client.upload_file(local_path, self.bucket, key)
            logger.info("Upload successful")
        except (NoCredentialsError, PartialCredentialsError) as cred_err:
            logger.error(f"AWS credentials error: {cred_err}")
            raise
        except ClientError as client_err:
            logger.error(f"S3 client error: {client_err}")
            raise
        except Exception as e:
            logger.error(f"Unexpected S3 upload error: {e}")
            raise
