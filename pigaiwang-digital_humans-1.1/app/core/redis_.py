"""Redis客户端模块。

提供Redis异步连接客户端和连接池管理：
- 异步Redis连接池初始化
- 全局Redis客户端实例
- 连接健康检查
- 自动重连机制
"""

from redis.asyncio import ConnectionPool, Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import (
    BusyLoadingError,
    ConnectionError,
    TimeoutError,
)

from app.configs.config import base_configs

# 定义需要重试的异常类型
RETRY_EXCEPTIONS = [
    ConnectionError,
    TimeoutError,
    BusyLoadingError,  # Redis 正在加载数据时
]

# 重试策略：指数退避，最多重试3次
retry_strategy = Retry(
    backoff=ExponentialBackoff(base=0.1, cap=2),  # 0.1s -> 0.2s -> 0.4s，最大2s
    retries=3,
)

redis_client_pool: ConnectionPool = ConnectionPool.from_url(
    base_configs.REDIS_URL,
    decode_responses=True,
    # === 连接池配置 ===
    max_connections=50,  # 最大连接数，根据并发量调整
    # === 超时配置 ===
    socket_timeout=5.0,  # 读写超时
    socket_connect_timeout=5.0,  # 连接超时
    # === 健康检查 ===
    health_check_interval=15,  # 每15秒检查连接健康
    # === TCP Keepalive（关键！） ===
    socket_keepalive=True,
    # === 重试配置 ===
    retry_on_timeout=True,
    retry_on_error=RETRY_EXCEPTIONS,
    retry=retry_strategy,
)

redis_client = Redis(
    connection_pool=redis_client_pool,
    single_connection_client=False,  # 使用连接池
)
