"""TaskIQ Broker 配置.

启动 worker 命令::

    taskiq worker app.tasks.broker:broker
"""

from taskiq import TaskiqEvents, TaskiqState
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from app.configs import base_configs
from app.utils.async_worker_id_allocator import worker_id_allocator
from app.utils.snowflake_id import snowflake_id_gen

from .executor import worker_executor
from .logging import setup_task_logger

broker = ListQueueBroker(
    url=base_configs.REDIS_URL,
).with_result_backend(
    RedisAsyncResultBackend(redis_url=base_configs.REDIS_URL, result_ex_time=600)
)


# ============================================================
# Worker 生命周期事件
# ============================================================


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def on_startup(state: TaskiqState) -> None:
    """Worker 启动时初始化资源

    注意：此事件只在 Worker 进程中触发，客户端进程不会触发。
    """
    print("获取 worker_id")
    base_configs.WORKER_ID = await worker_id_allocator.acquire()
    print(f"获取到 worker_id: {base_configs.WORKER_ID}")
    snowflake_id_gen.init_generator()
    setup_task_logger()
    print("[Broker] Worker 启动，初始化执行器...")

    try:
        worker_executor.start_pools()
    except Exception as e:
        print(f"[Broker] 初始化执行器失败: {e}, 退出")
        exit()
    print("[Broker] 执行器已启动:")
    # 新增：打印当前 broker 里注册的所有任务名称
    # 修正后的调试代码
    print("\n=== 当前 broker 已注册的任务列表 ===")
    registered_task_names = broker.get_all_tasks()  # 这里返回 list[str]

    if not registered_task_names:
        print("警告：broker 中没有任何任务被注册！")
    else:
        print(f"共注册 {len(registered_task_names)} 个任务：")
        for task_name in registered_task_names:
            print(f"  - {task_name}")
    print("=== 任务列表结束 ===\n")


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def on_shutdown(state: TaskiqState) -> None:
    """Worker 关闭时清理资源"""
    await worker_id_allocator.release()
    print("[Broker] Worker 关闭，停止执行器...")
    worker_executor.stop_pools()
    print("[Broker] 执行器已停止")
