"""雪花ID生成器模块.

提供分布式唯一ID生成功能：
- 基于Twitter Snowflake算法
- 64位整数格式，转字符串返回
- 使用进程ID作为机器标识
- 保证ID的全局唯一性和时间有序性
- 支持高并发场景下的ID生成

适用于数据库主键、订单号等需要唯一标识的场景。
"""

from snowflake import SnowflakeGenerator

from app.configs.config import base_configs


class SnowflakeIDGenerator:
    """雪花ID生成器."""

    def __init__(self):
        """初始化."""
        self.gen: SnowflakeGenerator

    def init_generator(self):
        """初始化雪花ID生成器."""
        self.gen = SnowflakeGenerator(base_configs.WORKER_ID)

    def generate_id(self) -> str:
        """生成雪花ID."""
        return str(next(self.gen))


snowflake_id_gen = SnowflakeIDGenerator()


def generate_id() -> str:
    """生成雪花ID.

    基于Twitter Snowflake算法生成分布式唯一ID.
    ID由时间戳、机器ID和序列号组成，保证全局唯一性和时间有序性。

    Returns:
        str: 64位雪花ID的字符串表示形式

    Note:
        - 机器ID使用当前进程ID对1023取模
        - 支持每毫秒生成4096个ID
        - ID按时间递增，适合用作数据库主键
    """
    return snowflake_id_gen.generate_id()
