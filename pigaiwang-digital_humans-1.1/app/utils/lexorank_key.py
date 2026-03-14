"""LexoRank 字符串级排序键工具。

提供面向业务的字符串级 API：直接输入/输出 `order_index`（或任何 rank 字段）的字符串值。

说明：
- LexoRank 算法用于“可插入排序（fractional indexing）”，支持在两条记录之间生成新的排序 key。
- 查询排序时不需要算法：数据库直接 `ORDER BY rank_field ASC` 即可。
- 只有在“插入到中间 / 拖拽重排 / 生成新 rank”时才需要调用本工具生成新字符串。

常见业务场景：
- 列表为空：插入第一条（`init_for_empty_list` / `insert(None, None)`）
- 追加到末尾：生成一个比最后一条更大的 key（`insert(prev=last, nxt=None)` / `insert_after`）
- 插入到中间：在前后两条之间生成 key（`insert(prev=left, nxt=right)` / `insert_between`）
- 插到最前：生成一个排在第一条之前的 key（`insert(prev=None, nxt=first)` / `insert_before`）

并发提醒：
- `insert_between(left, right)` 是确定性的：同一对 (left, right) 会生成同一个 key。
  如果多个请求并发往同一缝隙插入，可能产生重复 key（需要业务层加锁/重试/或在 DB 加唯一约束后处理冲突）。
"""

from __future__ import annotations

from typing import Optional

try:
    # 正常在项目包内使用：from app.utils.lexorank_key import LexoRankKey
    from .lexorank.lexo_rank import LexoRank
except ImportError:  # pragma: no cover
    # 允许在把 `app/utils` 加入 sys.path 后直接运行/测试：import lexorank_key
    from lexorank.lexo_rank import LexoRank  # type: ignore[no-redef]


class LexoRankKey:
    """业务入口类：把 rank 字符串的常用操作收敛到一个“命名空间”里。

    约定：
    - 所有公开方法入参/返回值都是字符串（来自 DB / 写回 DB）。
    - 该字符串本质上是 LexoRank 的序列化结果，例如：`0|hzzzzz:`

    你可以把它当成“任何需要可插入排序字段”的通用工具：
    - scripts.order_index
    - script_scenes.order_index
    - 未来其他需要中间插入/拖拽排序的字段

    注意：
    - 查询排序时不要用本工具：直接 `ORDER BY order_index ASC`。
    - 本工具只负责生成/校验 key，不负责写库与事务控制。
    """

    @staticmethod
    def insert(prev: Optional[str], nxt: Optional[str]) -> str:
        """通用插入：根据相邻前后记录的 rank 生成新 rank（最常用）。

        适用场景：
        - 分镜页/剧本页：拖拽排序（你通常能拿到“前一条”和“后一条”的 rank）
        - 在中间插入：prev 与 nxt 都有值
        - 插到最前：prev=None, nxt=first_rank
        - 追加到最后：prev=last_rank, nxt=None
        - 空列表插入第一条：prev=None, nxt=None

        Args:
            prev: 前一条记录的 rank；为 None 表示“插到最前”或“列表为空”。
            nxt: 后一条记录的 rank；为 None 表示“插到最后”或“列表为空”。

        Returns:
            str: 生成的新 rank 字符串，写回数据库即可参与排序。

        Raises:
            ValueError: prev/nxt 不是字符串、或 rank 格式非法、或两侧 rank 相等无法再细分。
        """
        prev = LexoRankKey._require_opt_str("prev", prev)
        nxt = LexoRankKey._require_opt_str("nxt", nxt)

        if prev is None and nxt is None:
            return LexoRankKey.init_for_empty_list()
        if prev is None:
            return LexoRankKey.insert_before(nxt)  # type: ignore[arg-type]
        if nxt is None:
            return LexoRankKey.insert_after(prev)
        return LexoRankKey.insert_between(prev, nxt)

    @staticmethod
    def insert_between(left: str, right: str) -> str:
        """在两条记录之间插入（常用：拖拽排序/中间插入）。

        适用场景：
        - 你明确知道要插在 left 和 right 中间（两条相邻或将要相邻的记录）。

        注意：
        - 这是确定性函数：相同的 left/right 会生成相同的新 rank。
          如果并发插入同一缝隙，可能发生重复 key（建议加唯一约束并在冲突时重试）。
        - left/right 必须属于同一 bucket（一般你都在 bucket=0 内，不需要关心）。

        Args:
            left: 左侧记录的 rank（较小）。
            right: 右侧记录的 rank（较大）。

        Returns:
            str: 严格位于两者之间的新 rank。
        """
        left = LexoRankKey._require_str("left", left)
        right = LexoRankKey._require_str("right", right)
        return str(LexoRank.parse(left).between(LexoRank.parse(right)))

    @staticmethod
    def insert_after(anchor: str) -> str:
        """在某条记录之后插入（常用：连续追加到末尾）。

        适用场景：
        - 你只知道“最后一条”的 rank，需要新纪录排在最后。
        - 连续追加时，用 `insert_after(last_rank)` 会非常方便。

        注意：
        - 当 anchor 已接近 bucket 上界时，`gen_next()` 可能抛错（极端情况）。
          一般列表规模下不太会触发；如果触发通常意味着 rank 太密，需要做一次“重排/重新编号”。
        """
        anchor = LexoRankKey._require_str("anchor", anchor)
        return str(LexoRank.parse(anchor).gen_next())

    @staticmethod
    def insert_before(anchor: str) -> str:
        """在某条记录之前插入（较少用：插到最前或前插）。

        适用场景：
        - 你只知道“第一条”的 rank，需要新纪录排在最前。

        注意：
        - 长期反复在最前插入，会让 rank 字符串变长（这是 fractional indexing 的正常现象）。
        """
        anchor = LexoRankKey._require_str("anchor", anchor)
        return str(LexoRank.min().between(LexoRank.parse(anchor)))

    @staticmethod
    def init_for_empty_list() -> str:
        """空列表插入第一条记录时使用（较常用）。

        适用场景：
        - 该列表当前没有任何元素（例如某个 project 下还没有 scripts）。

        Returns:
            str: 适合作为第一条记录的 rank（通常是 bucket=0 的“中间值”）。
        """
        return str(LexoRank.middle())

    @staticmethod
    def next_of(current: str) -> str:
        """生成一个比 current 更大的 rank（不常用：等价于 insert_after）。

        适用场景：
        - 你已经有 current 的 rank，想快速得到一个更大的 rank（例如后台修复/调试）。
        """
        current = LexoRankKey._require_str("current", current)
        return str(LexoRank.parse(current).gen_next())

    @staticmethod
    def prev_of(current: str) -> str:
        """生成一个比 current 更小的 rank（不常用：需要谨慎）。

        适用场景：
        - 你想得到一个排在 current 之前的 rank，但又不想/不能提供 next（右邻居）。

        注意：
        - 如果 current 已经是全局最小值附近，可能会抛错（边界行为）。
          一般业务更推荐用 `insert_before(first_rank)`，而不是 `prev_of(first_rank)`。
        """
        current = LexoRankKey._require_str("current", current)
        return str(LexoRank.parse(current).gen_prev())

    @staticmethod
    def validate(value: str) -> str:
        """校验字符串是否为合法 LexoRank key（不常用：输入校验/数据修复）。

        适用场景：
        - 导入数据时，校验 `order_index` 是否是合法 LexoRank 格式。
        - 数据修复工具：扫描 DB 中的 rank 字段，发现非法值就报警。

        Returns:
            str: 如果合法，原样返回（便于链式调用）。

        Raises:
            ValueError: value 不是字符串或不是合法 LexoRank。
        """
        value = LexoRankKey._require_str("value", value)
        LexoRank.parse(value)
        return value

    # --- 内部校验工具（业务代码不需要调用） ---

    @staticmethod
    def _require_str(name: str, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError(
                f"{name} must be a str rank value, got {type(value).__name__}"
            )
        return value

    @staticmethod
    def _require_opt_str(name: str, value: object | None) -> str | None:
        if value is None:
            return None
        return LexoRankKey._require_str(name, value)
