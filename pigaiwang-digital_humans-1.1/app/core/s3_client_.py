"""异步S3存储操作模块。

基于aioboto3的轻量封装，支持大文件分片上传下载。

依赖安装:
    pip install aioboto3

Example:
    from app.configs.config import base_configs
    s3 = S3Client(
        endpoint=base_configs.S3_URL,
        access_key=base_configs.S3_ACCESS_KEY,
        secret_key=base_configs.S3_SECRET_KEY,
        region=base_configs.S3_REGION,
        max_pool_connections=base_configs.S3_MAX_POOL_CONNECTIONS,
        multipart_threshold=base_configs.S3_MULTIPART_THRESHOLD,
        multipart_chunksize=base_configs.S3_MULTIPART_CHUNKSIZE,
        max_concurrency=base_configs.S3_MAX_CONCURRENCY,
    )

    async with s3.client() as c:
        # 小文件
        await c.put_object(Bucket="bucket", Key="key", Body=b"data")

        # 大文件（自动分片）
        with open("large.zip", "rb") as fp:
            await c.upload_fileobj(fp, "bucket", "key", Config=s3.transfer_config)
"""

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import BinaryIO

import aioboto3
from aiobotocore.config import AioConfig
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError

from app.common.enums import BucketMenu
from app.configs.config import base_configs


class S3Client:
    """异步S3客户端。

    轻量封装，支持大文件分片传输。Session类级别共享，
    client按需创建，底层连接池由aiohttp管理。

    Args:
        endpoint: S3服务端点URL。
        access_key: 访问密钥。
        secret_key: 秘密密钥。
        region: 区域，默认"us-east-1"。
        max_pool_connections: 最大连接数，默认50。
        multipart_threshold: 分片上传阈值（字节），默认8MB。
        multipart_chunksize: 分片大小（字节），默认8MB。
        max_concurrency: 分片传输并发数，默认10。

    Example:
        s3 = S3Client("http://localhost:9000", "ak", "sk")

        # 使用原生API
        async with s3.client() as c:
            await c.put_object(Bucket="b", Key="k", Body=b"data")

            # 大文件上传（自动分片）
            with open("large.zip", "rb") as fp:
                await c.upload_fileobj(fp, "bucket", "key", Config=s3.transfer_config)

        # 使用便捷方法
        await s3.upload("bucket", "key", "/path/to/large/file")
    """

    _session: aioboto3.Session = aioboto3.Session()

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        max_pool_connections: int = 50,
        multipart_threshold: int = 8 * 1024 * 1024,
        multipart_chunksize: int = 8 * 1024 * 1024,
        max_concurrency: int = 10,
    ):
        """初始化对象，配置客户端连接参数和传输设置

        Args:
            endpoint (str): 服务端点URL地址
            access_key (str): 访问密钥ID，用于身份验证
            secret_key (str): 秘密访问密钥，用于身份验证
            region (str, optional): 服务区域标识符. Defaults to "us-east-1".
            max_pool_connections (int, optional): 连接池最大连接数. Defaults to 50.
            multipart_threshold (int, optional): 触发分片上传的文件大小阈值(字节). Defaults to 8*1024*1024.
            multipart_chunksize (int, optional): 分片上传时每个分片的大小(字节). Defaults to 8*1024*1024.
            max_concurrency (int, optional): 最大并发数. Defaults to 10.
        """
        self._client_config = {
            "endpoint_url": endpoint,
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "region_name": region,
            "config": AioConfig(
                max_pool_connections=max_pool_connections,
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "adaptive"},
            ),
        }

        # 大文件传输配置
        self.transfer_config = TransferConfig(
            multipart_threshold=multipart_threshold,
            multipart_chunksize=multipart_chunksize,
            max_concurrency=max_concurrency,
            use_threads=True,
        )

    async def init_buckets(self):
        """初始化存储桶"""
        bucket_names = {bucket.value for bucket in BucketMenu}
        for attr_name in (
            "QUESTION_IMAGE_BUCKET",
            "QUESTION_S3_BUCKET",
            "S3_BUCKET_NAME",
            "S3_BUCKET",
            "RUSTFS_BUCKET",
        ):
            bucket_name = getattr(base_configs, attr_name, None)
            if bucket_name:
                bucket_names.add(str(bucket_name))

        async with self.client() as c:
            for bucket_name in bucket_names:
                try:
                    await c.create_bucket(Bucket=bucket_name)
                    print(f"✓ 创建桶: {bucket_name}")
                except Exception as e:
                    if "BucketAlreadyOwnedByYou" in str(e):
                        pass
                    else:
                        print(f"❌ 创建桶失败: {bucket_name}", e)

                if getattr(base_configs, "S3_PUBLIC_READ_POLICY", False):
                    try:
                        policy = {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Sid": "PublicReadGetObject",
                                    "Effect": "Allow",
                                    "Principal": "*",
                                    "Action": ["s3:GetObject"],
                                    "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
                                }
                            ],
                        }
                        await c.put_bucket_policy(
                            Bucket=bucket_name,
                            Policy=json.dumps(policy, ensure_ascii=False),
                        )
                        print(f"✓ 设置桶公开读策略: {bucket_name}")
                    except Exception as e:
                        print(f"❌ 设置桶公开读策略失败: {bucket_name}", e)

    def get_public_endpoint(self) -> str:
        public_url = getattr(base_configs, "S3_PUBLIC_URL", None)
        if public_url:
            return str(public_url).rstrip("/")
        return str(base_configs.S3_URL).rstrip("/")

    def build_public_object_url(self, bucket: str, key: str) -> str:
        return f"{self.get_public_endpoint()}/{bucket}/{key.lstrip('/')}"

    def extract_object_key_from_url(self, image_url: str, bucket: str) -> str | None:
        normalized = (image_url or "").strip()
        if not normalized:
            return None

        candidate_prefixes = [
            f"{self.get_public_endpoint()}/{bucket}/",
            f"{str(base_configs.S3_URL).rstrip('/')}\/{bucket}/".replace("\\/", "/"),
        ]
        for prefix in candidate_prefixes:
            if normalized.startswith(prefix):
                return normalized[len(prefix):]
        return None

    async def resolve_download_url(
        self,
        image_url: str,
        bucket: str,
        expires: int | None = None,
    ) -> str:
        normalized = (image_url or "").strip()
        if not normalized:
            return normalized

        object_key = self.extract_object_key_from_url(normalized, bucket)
        if object_key is None:
            return normalized

        if getattr(base_configs, "S3_USE_PRESIGNED_DOWNLOAD_URL", False):
            expires_in = int(
                expires
                or getattr(base_configs, "S3_PRESIGNED_DOWNLOAD_EXPIRES", 3600)
            )
            return await self.presign_download(bucket, object_key, expires=expires_in)

        return self.build_public_object_url(bucket, object_key)

    @asynccontextmanager
    async def client(self):
        """获取S3 client。

        Yields:
            aioboto3 S3 client，支持所有原生API。

        Example:
            async with s3.client() as c:
                await c.put_object(Bucket="b", Key="k", Body=b"data")
                await c.list_buckets()
        """
        async with self._session.client("s3", **self._client_config) as c:
            yield c

    # ==================== 文件上传下载（支持大文件） ====================

    async def upload_file(
        self,
        bucket: str,
        key: str,
        filepath: str | Path,
        content_type: str | None = None,
    ) -> None:
        """上传文件（大文件自动分片）。

        Args:
            bucket: 桶名称。
            key: 对象键。
            filepath: 本地文件路径。
            content_type: 内容类型。
        """
        if type(filepath) is not Path:
            filepath = Path(filepath)
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        async with self.client() as c:
            with filepath.open("rb") as fp:
                await c.upload_fileobj(
                    fp,
                    bucket,
                    key,
                    ExtraArgs=extra_args or None,
                    Config=self.transfer_config,
                )

    async def upload_fileobj(
        self,
        bucket: str,
        key: str,
        fileobj: BinaryIO,
        content_type: str | None = None,
    ) -> None:
        """上传文件对象（大文件自动分片）。

        Args:
            bucket: 桶名称。
            key: 对象键。
            fileobj: 文件对象（支持read）。
            content_type: 内容类型。
        """
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        async with self.client() as c:
            await c.upload_fileobj(
                fileobj,
                bucket,
                key,
                ExtraArgs=extra_args or None,
                Config=self.transfer_config,
            )

    async def download_file(
        self,
        bucket: str,
        key: str,
        filepath: str | Path,
    ) -> None:
        """下载文件（大文件自动分片）。

        Args:
            bucket: 桶名称。
            key: 对象键。
            filepath: 本地保存路径。
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        async with self.client() as c:
            with filepath.open("wb") as fp:
                await c.download_fileobj(
                    bucket,
                    key,
                    fp,
                    Config=self.transfer_config,
                )

    async def download_fileobj(
        self,
        bucket: str,
        key: str,
        fileobj: BinaryIO,
    ) -> None:
        """下载到文件对象（大文件自动分片）。

        Args:
            bucket: 桶名称。
            key: 对象键。
            fileobj: 文件对象（支持write）。
        """
        async with self.client() as c:
            await c.download_fileobj(
                bucket,
                key,
                fileobj,
                Config=self.transfer_config,
            )

    # ==================== 简单操作（小数据） ====================

    async def put(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str | None = None,
    ) -> None:
        """上传字节数据（适合小数据）。

        Args:
            bucket: 桶名称。
            key: 对象键。
            data: 字节数据。
            content_type: 内容类型。
        """
        kwargs = {"Bucket": bucket, "Key": key, "Body": data}
        if content_type:
            kwargs["ContentType"] = content_type

        async with self.client() as c:
            await c.put_object(**kwargs)

    async def get(self, bucket: str, key: str) -> bytes:
        """下载为字节（适合小数据）。

        Args:
            bucket: 桶名称。
            key: 对象键。

        Returns:
            对象内容。
        """
        async with self.client() as c:
            resp = await c.get_object(Bucket=bucket, Key=key)
            async with resp["Body"] as stream:
                return await stream.read()

    async def delete(self, bucket: str, key: str) -> None:
        """删除对象。

        Args:
            bucket: 桶名称。
            key: 对象键。
        """
        async with self.client() as c:
            await c.delete_object(Bucket=bucket, Key=key)

    async def exists(self, bucket: str, key: str) -> bool:
        """检查对象是否存在。

        Args:
            bucket: 桶名称。
            key: 对象键。

        Returns:
            存在返回True。
        """
        async with self.client() as c:
            try:
                await c.head_object(Bucket=bucket, Key=key)
                return True
            except ClientError:
                return False

    async def presign_upload(
        self,
        bucket: str,
        key: str,
        expires: int = 3600,
    ) -> str:
        """生成上传预签名URL。

        Args:
            bucket: 桶名称。
            key: 对象键。
            expires: 有效期（秒）。

        Returns:
            预签名URL。
        """
        async with self.client() as c:
            return await c.generate_presigned_url(
                "put_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires,
            )

    async def presign_download(
        self,
        bucket: str,
        key: str,
        expires: int = 3600,
    ) -> str:
        """生成下载预签名URL。

        Args:
            bucket: 桶名称。
            key: 对象键。
            expires: 有效期（秒）。

        Returns:
            预签名URL。
        """
        async with self.client() as c:
            return await c.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires,
            )


s3_client = S3Client(
    endpoint=base_configs.S3_URL,
    access_key=base_configs.S3_ACCESS_KEY,
    secret_key=base_configs.S3_SECRET_KEY,
    region=base_configs.S3_REGION,
    max_pool_connections=base_configs.S3_MAX_POOL_CONNECTIONS,
    multipart_threshold=base_configs.S3_MULTIPART_THRESHOLD,
    multipart_chunksize=base_configs.S3_MULTIPART_CHUNKSIZE,
    max_concurrency=base_configs.S3_MAX_CONCURRENCY,
)
