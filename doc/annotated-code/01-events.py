"""
消息总线的事件类型定义 (阶段 1-2 核心文件)

这个模块定义了 nanobot 消息总线中使用的核心数据结构：
- InboundMessage: 从聊天平台接收的消息
- OutboundMessage: 发送到聊天平台的消息

这些数据类使用 @dataclass 装饰器，自动生成 __init__、__repr__ 等方法。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class InboundMessage:
    """
    接收的消息（从聊天平台到 Agent）

    这个类表示从各种聊天平台（Telegram、Discord、Slack 等）接收到的消息。
    消息总线会将这些消息路由到 Agent Loop 进行处理。

    属性说明：
        channel: 消息来源的聊天平台（如 "telegram", "discord", "slack"）
        sender_id: 发送者的唯一标识符（用户 ID）
        chat_id: 聊天会话的唯一标识符（可能是私聊 ID 或群组 ID）
        content: 消息的文本内容
        timestamp: 消息接收时间（默认为当前时间）
        media: 媒体文件的 URL 列表（图片、视频等）
        metadata: 平台特定的额外数据（如消息 ID、回复信息等）
    """

    channel: str  # 聊天平台名称：telegram, discord, slack, whatsapp 等
    sender_id: str  # 发送者 ID，用于识别用户身份
    chat_id: str  # 聊天 ID，用于识别对话会话（私聊或群聊）
    content: str  # 消息文本内容
    timestamp: datetime = field(default_factory=datetime.now)  # 消息时间戳
    media: list[str] = field(default_factory=list)  # 媒体文件 URL 列表
    metadata: dict[str, Any] = field(default_factory=dict)  # 平台特定的元数据

    @property
    def session_key(self) -> str:
        """
        生成会话的唯一标识符

        会话键用于：
        1. 区分不同的对话会话
        2. 加载和保存会话历史
        3. 管理多用户并发对话

        格式: "平台名:聊天ID"
        例如: "telegram:123456789" 或 "discord:987654321"

        返回:
            str: 格式为 "channel:chat_id" 的唯一会话标识符
        """
        return f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """
    发送的消息（从 Agent 到聊天平台）

    这个类表示 Agent 处理完成后要发送到聊天平台的消息。
    消息总线会将这些消息路由到对应的 Channel 进行发送。

    属性说明：
        channel: 目标聊天平台
        chat_id: 目标聊天会话 ID
        content: 要发送的文本内容
        reply_to: 要回复的消息 ID（可选）
        media: 要发送的媒体文件 URL 列表
        metadata: 平台特定的发送选项（如是否静音、是否预览链接等）
    """

    channel: str  # 目标聊天平台
    chat_id: str  # 目标聊天 ID
    content: str  # 要发送的消息内容
    reply_to: str | None = None  # 回复的消息 ID（如果是回复消息）
    media: list[str] = field(default_factory=list)  # 要发送的媒体文件 URL
    metadata: dict[str, Any] = field(default_factory=dict)  # 平台特定的发送选项
