"""管理线程池与进程池的执行器"""

import asyncio
import multiprocessing
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.pool import Pool

from loguru import logger

from app.utils.sync_worker_id_allocator import init_subprocess_worker_id

from .config import task_config


def init_worker_executor() -> None:
    """初始化执行器 (运行在子进程中)."""
    print("初始化 worker_id")

    # 导入需要在子进程中使用的配置
    from app.configs import base_configs
    from app.utils.snowflake_id import snowflake_id_gen

    # log = logger.bind(log_type="system")

    # 初始化 Worker ID
    base_configs.WORKER_ID = init_subprocess_worker_id(base_configs.REDIS_URL)
    print(
        f"✅ [子进程 {os.getpid()}] 获取到 worker_id，用于通用多进程任务: {base_configs.WORKER_ID}"
    )
    # 初始化 Snowflake ID 生成器
    snowflake_id_gen.init_generator()


class Executor:
    """管理线程池与进程池的执行器 (针对 Windows 内存泄漏优化版)"""

    def __init__(self):
        """初始化函数"""
        self._process_pool: Pool
        self._thread_pool: ThreadPoolExecutor
        # [新增] 用于统计调用次数的字典
        self._call_counters = defaultdict(int)

    def start_pools(self) -> None:
        """启动池，使用 maxtasksperchild 防止内存泄漏"""
        # 1. 通用计算池 (设置 maxtasksperchild=20，频繁重启以释放碎片)
        self._process_pool = multiprocessing.Pool(
            processes=task_config.PROCESS_POOL_SIZE,
            initializer=init_worker_executor,
            maxtasksperchild=2000,  # <--- 关键：处理20个任务后重启进程
        )

        self._thread_pool = ThreadPoolExecutor(max_workers=task_config.THREAD_POOL_SIZE)
        # 重置计数器
        self._call_counters.clear()
        logger.info("✅ 所有进程池/线程池已启动")

    def stop_pools(self) -> None:
        """停止所有线程池"""
        # multiprocessing.Pool 的关闭方式不同
        if self._process_pool:
            self._process_pool.close()
            self._process_pool.join()
        if self._thread_pool:
            self._thread_pool.shutdown(wait=True)

    # ---------------------------------------------------------
    # 修改：桥接 asyncio 和 multiprocessing.Pool 的辅助方法
    # ---------------------------------------------------------
    async def run_in_mp_pool(self, pool, func, *args):
        """在 multiprocessing.Pool 中运行同步函数，并 await 结果。"""
        # [新增] 1. 识别当前使用的是哪个池子
        # if pool is self._process_pool:
        #     pool_name = "🟢 通用计算池 (Process)"

        # # [新增] 2. 计数
        # self._call_counters[pool_name] += 1
        # count = self._call_counters[pool_name]

        # [新增] 3. 打印日志 (显示池名字、当前第几次调用、调用的函数名)
        # func.__name__ 可以获取当前执行的函数名，如 _sync_cpu_split
        # logger.info(f"[{pool_name}] 第 {count} 次调用 | 执行任务: {func.__name__}")

        loop = asyncio.get_running_loop()
        # 注意：这里我们把 pool.apply 放到线程池里去跑
        return await loop.run_in_executor(None, lambda: pool.apply(func, args))


worker_executor = Executor()
