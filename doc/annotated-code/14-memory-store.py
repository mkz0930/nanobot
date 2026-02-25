"""
记忆系统 - Agent 的长期记忆和日记

这个模块实现了 Agent 的记忆系统。
记忆系统允许 Agent 记住重要信息并在未来的对话中使用。

核心概念：
1. 长期记忆（MEMORY.md）- 永久保存的重要信息
2. 日记（YYYY-MM-DD.md）- 每天的记录
3. 上下文加载 - 自动加载到系统提示中

记忆存储结构：
workspace/
  memory/
    MEMORY.md           # 长期记忆
    2024-01-15.md       # 今天的日记
    2024-01-14.md       # 昨天的日记
    ...

使用场景：
1. 用户偏好 - "我喜欢简洁的回答"
2. 项目信息 - "这个项目使用 Python 3.11"
3. 重要事件 - "2024-01-15: 完成了新功能"
4. 待办事项 - "记得明天提醒我..."

设计思路：
- 简单 - 使用 Markdown 文件，人类可读
- 灵活 - Agent 可以自由组织内容
- 持久 - 文件永久保存
- 自动 - 自动加载到上下文中
"""

from pathlib import Path
from datetime import datetime

from nanobot.utils.helpers import ensure_dir, today_date


class MemoryStore:
    """
    记忆存储

    职责：
    1. 长期记忆管理 - 读写 MEMORY.md
    2. 日记管理 - 读写每日记录
    3. 上下文构建 - 为 Agent 提供记忆上下文

    文件格式：
    - MEMORY.md: 自由格式的 Markdown
    - YYYY-MM-DD.md: 每日记录（自动添加日期标题）

    Agent 如何使用记忆？
    1. 系统提示中包含记忆内容
    2. Agent 可以使用 write_file 工具更新记忆
    3. Agent 可以使用 read_file 工具查看历史记录
    """

    def __init__(self, workspace: Path):
        """
        初始化记忆存储

        参数:
            workspace: 工作区路径（~/.nanobot/workspace/）
        """
        self.workspace = workspace
        # 记忆目录（workspace/memory/）
        self.memory_dir = ensure_dir(workspace / "memory")
        # 长期记忆文件
        self.memory_file = self.memory_dir / "MEMORY.md"

    def get_today_file(self) -> Path:
        """
        获取今天的日记文件路径

        返回:
            Path: 今天的日记文件（如 2024-01-15.md）

        使用示例：
        ```python
        today_file = memory.get_today_file()
        # Path: workspace/memory/2024-01-15.md
        ```
        """
        return self.memory_dir / f"{today_date()}.md"

    def read_today(self) -> str:
        """
        读取今天的日记

        返回:
            str: 今天的日记内容（如果不存在返回空字符串）

        使用场景：
        - Agent 查看今天已经记录的内容
        - 避免重复记录
        """
        today_file = self.get_today_file()
        if today_file.exists():
            return today_file.read_text(encoding="utf-8")
        return ""

    def append_today(self, content: str) -> None:
        """
        追加内容到今天的日记

        如果今天的日记不存在，会自动创建并添加日期标题。

        参数:
            content: 要追加的内容

        使用示例：
        ```python
        memory.append_today("## 10:30 - 完成了新功能\\n\\n...")
        ```

        文件格式：
        ```markdown
        # 2024-01-15

        ## 10:30 - 完成了新功能
        ...

        ## 14:00 - 修复了 Bug
        ...
        ```
        """
        today_file = self.get_today_file()

        if today_file.exists():
            # 追加到已有内容
            existing = today_file.read_text(encoding="utf-8")
            content = existing + "\n" + content
        else:
            # 创建新文件，添加日期标题
            header = f"# {today_date()}\n\n"
            content = header + content

        today_file.write_text(content, encoding="utf-8")

    def read_long_term(self) -> str:
        """
        读取长期记忆

        返回:
            str: MEMORY.md 的内容（如果不存在返回空字符串）

        长期记忆内容示例：
        ```markdown
        # 用户偏好
        - 喜欢简洁的回答
        - 使用中文交流

        # 项目信息
        - 使用 Python 3.11
        - 主要框架：FastAPI

        # 重要联系人
        - 张三：项目经理
        ```
        """
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def write_long_term(self, content: str) -> None:
        """
        写入长期记忆

        覆盖 MEMORY.md 的内容。

        参数:
            content: 新的记忆内容

        使用场景：
        - Agent 整理和更新记忆
        - 用户手动编辑记忆文件

        注意：
        - 会覆盖已有内容
        - 建议 Agent 先读取再更新
        """
        self.memory_file.write_text(content, encoding="utf-8")

    def get_recent_memories(self, days: int = 7) -> str:
        """
        获取最近几天的日记

        参数:
            days: 回溯天数（默认 7 天）

        返回:
            str: 合并的日记内容

        使用场景：
        - Agent 回顾最近的活动
        - 生成周报或总结

        示例：
        ```python
        # 获取最近 7 天的日记
        recent = memory.get_recent_memories(7)
        ```
        """
        from datetime import timedelta

        memories = []
        today = datetime.now().date()

        # 从今天往前回溯
        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            file_path = self.memory_dir / f"{date_str}.md"

            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                memories.append(content)

        # 用分隔符连接
        return "\n\n---\n\n".join(memories)

    def list_memory_files(self) -> list[Path]:
        """
        列出所有日记文件

        返回:
            list[Path]: 日记文件列表（按日期倒序）

        使用场景：
        - 管理界面显示所有日记
        - 清理旧日记
        """
        if not self.memory_dir.exists():
            return []

        # 匹配格式：YYYY-MM-DD.md
        files = list(self.memory_dir.glob("????-??-??.md"))
        # 按日期倒序排序（最新的在前）
        return sorted(files, reverse=True)

    def get_memory_context(self) -> str:
        """
        获取记忆上下文（用于系统提示）

        这个方法被 ContextBuilder 调用，将记忆加载到系统提示中。

        返回:
            str: 格式化的记忆上下文

        包含内容：
        1. 长期记忆（MEMORY.md）
        2. 今天的日记

        为什么只包含今天的日记？
        - 节省 token
        - 今天的内容最相关
        - Agent 可以使用 read_file 查看历史日记

        格式：
        ```markdown
        ## Long-term Memory
        [MEMORY.md 的内容]

        ## Today's Notes
        [今天的日记内容]
        ```
        """
        parts = []

        # 1. 长期记忆
        long_term = self.read_long_term()
        if long_term:
            parts.append("## Long-term Memory\n" + long_term)

        # 2. 今天的日记
        today = self.read_today()
        if today:
            parts.append("## Today's Notes\n" + today)

        return "\n\n".join(parts) if parts else ""
