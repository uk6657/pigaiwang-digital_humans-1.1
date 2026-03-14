"""一个使用broker注册任务的示例，开发时请删除!!!"""

import asyncio

from app.tasks.broker import broker


@broker.task(task_name="broker_tasks:test_task")
async def test_task(x: int, y: int) -> int:
    """一个简单的加法任务.

    Args:
        x: 第一个加数
        y: 第二个加数

    Returns:
        两数之和

    Example:
        提交任务::

            from app.tasks.broker_tasks.test import test_task

            result = await test_task.delay(3, 5)
            sum_value = await result.get_result()
            print(f"3 + 5 = {sum_value}")  # 输出: 3 + 5 = 8
    """
    await asyncio.sleep(3)
    return x + y
