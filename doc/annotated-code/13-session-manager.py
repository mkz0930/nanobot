"""
会话管理器 - 管理多用户对话历史

这个模块负责管理所有用户的对话会话。
每个会话包含一个用户与 Agent 的完整对话历史。

核心概念：
1. 会话（Session）- 一个用户的对话历史
2. 会话键（Session Key）- 唯一标识符（格式：channel:chat_id）
3. 持久化 - 会话保存为 JSONL 文件
4. 缓存 - 内存中缓存活跃会话

会话存储：
~/.nanobot/sessions/
  telegram_123456789.jsonl  # Telegram 用户的会话
  discord_987654321.jsonl   # Discord 用户的会话

JSONL 格式：
每行一个 JSON 对象，表示一条消息：
{"role": "user", "content": "Hello", "timestamp": "2024-01-15T10:30:00"}
{"role": "assistant", "content": "Hi!", "timestamp": "2024-01-15T10:30:05"}

设计思路：
- 简单可靠 - JSONL 格式易于读写和调试
- 高效 - 内存缓存减少磁盘 I/O
- 可扩展 - 支持元数据存储
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

from nanobot.utils.helpers import ensure_dir, safe_filename


@dataclass
class Session:
    """
    对话会话

    表示一个用户与 Agent 的完整对话历史。

    属性：
        key: 会话键（格式：channel:chat_id）
        messages: 消息列表（包含 role, content, timestamp 等）
        created_at: 会话创建时间
        updated_at: 最后更新时间
        metadata: 会话元数据（可存储任意信息）

    消息格式：
    {
        "role": "user" | "assistant" | "system" | "tool",
        "content": "消息内容",
        "timestamp": "2024-01-15T10:30:00",
        ... 其他字段
    }
    """

    key: str  # 会话键：channel:chat_id
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """
        添加消息到会话

        参数:
            role: 消息角色（user, assistant, system, tool）
            content: 消息内容
            **kwargs: 其他字段（如 tool_calls, reasoning_content 等）

        使用示例：
        ```python
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi! How can I help?")
        session.add_message("tool", "File content...", tool_call_id="123")
        ```
        """
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.messages.append(msg)
        self.updated_at = datetime.now()

    def get_history(self, max_messages: int = 50) -> list[dict[str, Any]]:
        """
        获取消息历史（用于 LLM 上下文）

        只返回最近的消息，避免上下文过长。
        只包含 role 和 content 字段（LLM 需要的格式）。

        参数:
            max_messages: 最大消息数量（默认 50）

        返回:
            list[dict]: LLM 格式的消息列表
            [
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "..."}
            ]

        为什么限制消息数量？
        - LLM 有上下文长度限制
        - 太长的历史会增加成本和延迟
        - 通常最近的对话最相关
        """
        # 获取最近的消息
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages

        # 转换为 LLM 格式（只保留 role 和 content）
        return [{"role": m["role"], "content": m["content"]} for m in recent]

    def clear(self) -> None:
        """
        清空会话历史

        用于 /reset 命令或用户请求重置对话。

        注意：
        - 清空后无法恢复
        - 会话文件会被覆盖
        """
        self.messages = []
        self.updated_at = datetime.now()


class SessionManager:
    """
    会话管理器

    职责：
    1. 会话创建 - 为新用户创建会话
    2. 会话加载 - 从磁盘加载已有会话
    3. 会话保存 - 将会话持久化到磁盘
    4. 会话缓存 - 在内存中缓存活跃会话

    存储格式：
    - 每个会话一个 JSONL 文件
    - 文件名：{channel}_{chat_id}.jsonl
    - 每行一个 JSON 对象（一条消息）

    为什么使用 JSONL？
    - 简单 - 易于读写和调试
    - 追加友好 - 可以直接追加新消息
    - 人类可读 - 可以用文本编辑器查看
    - 容错性好 - 单行损坏不影响其他行
    """

    def __init__(self, workspace: Path):
        """
        初始化会话管理器

        参数:
            workspace: 工作区路径（~/.nanobot/workspace/）
        """
        self.workspace = workspace
        # 会话存储目录（~/.nanobot/sessions/）
        self.sessions_dir = ensure_dir(Path.home() / ".nanobot" / "sessions")
        # 内存缓存（key -> Session）
        self._cache: dict[str, Session] = {}

    def _get_session_path(self, key: str) -> Path:
        """
        获取会话文件路径

        将会话键转换为安全的文件名。
        例如：telegram:123456789 → telegram_123456789.jsonl

        参数:
            key: 会话键（channel:chat_id）

        返回:
            Path: 会话文件路径
        """
        # 替换冒号为下划线，确保文件名安全
        safe_key = safe_filename(key.replace(":", "_"))
        return self.sessions_dir / f"{safe_key}.jsonl"

    def get_or_create(self, key: str) -> Session:
        """
        获取或创建会话

        如果会话已存在（在缓存或磁盘），返回已有会话。
        否则创建新会话。

        参数:
            key: 会话键（channel:chat_id）

        返回:
            Session: 会话对象

        使用示例：
        ```python
        # 在 Agent Loop 中
        session = session_manager.get_or_create("telegram:123456789")
        history = session.get_history()
        ```

        缓存策略：
        1. 检查内存缓存
        2. 如果不在缓存，尝试从磁盘加载
        3. 如果磁盘也没有，创建新会话
        4. 将会话加入缓存
        """
        # 1. 检查缓存
        if key in self._cache:
            return self._cache[key]

        # 2. 尝试从磁盘加载
        session = self._load(key)
        if session is None:
            # 3. 创建新会话
            session = Session(key=key)

        # 4. 加入缓存
        self._cache[key] = session
        return session

    def _load(self, key: str) -> Session | None:
        """
        从磁盘加载会话

        读取 JSONL 文件并重建 Session 对象。

        参数:
            key: 会话键

        返回:
            Session | None: 会话对象或 None（如果不存在）

        JSONL 格式：
        {"role": "user", "content": "Hello", "timestamp": "..."}
        {"role": "assistant", "content": "Hi!", "timestamp": "..."}
        """
        path = self._get_session_path(key)
        if not path.exists():
            return None

        try:
            messages = []
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        messages.append(json.loads(line))

            return Session(key=key, messages=messages)
        except Exception as e:
            logger.error(f"Failed to load session {key}: {e}")
            return None

    def save(self, session: Session) -> None:
        """
        保存会话到磁盘

        将会话写入 JSONL 文件。

        参数:
            session: 要保存的会话

        使用示例：
        ```python
        # 在 Agent Loop 中
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi!")
        session_manager.save(session)
        ```

        注意：
        - 会覆盖已有文件
        - 如果保存失败，会记录错误日志
        """
        path = self._get_session_path(session.key)

        try:
            with path.open("w", encoding="utf-8") as f:
                for msg in session.messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to save session {session.key}: {e}")

    def delete(self, key: str) -> None:
        """
        删除会话

        从缓存和磁盘中删除会话。

        参数:
            key: 会话键

        使用场景：
        - 用户请求删除历史
        - 清理旧会话
        """
        # 从缓存中删除
        self._cache.pop(key, None)

        # 从磁盘中删除
        path = self._get_session_path(key)
        if path.exists():
            path.unlink()

    def list_sessions(self) -> list[str]:
        """
        列出所有会话

        返回:
            list[str]: 会话键列表

        用途：
        - 管理界面显示所有会话
        - 清理旧会话
        """
        if not self.sessions_dir.exists():
            return []

        sessions = []
        for path in self.sessions_dir.glob("*.jsonl"):
            # 从文件名恢复会话键
            key = path.stem.replace("_", ":", 1)
            sessions.append(key)

        return sessions
