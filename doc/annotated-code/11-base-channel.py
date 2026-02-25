"""
Channel 基类 - 聊天平台集成的抽象接口

这个模块定义了所有聊天平台（Telegram、Discord、Slack 等）的统一接口。
每个聊天平台都需要实现这个基类来集成到 nanobot。

核心概念：
1. 统一接口 - 所有平台使用相同的接口
2. 消息总线 - 通过 MessageBus 与 Agent 通信
3. 访问控制 - 支持白名单（allowFrom）
4. 异步处理 - 所有操作都是异步的

Channel 的职责：
1. 连接到聊天平台
2. 接收平台消息并转换为 InboundMessage
3. 将 OutboundMessage 发送到平台
4. 管理连接状态和资源

消息流程：
┌──────────────┐
│ 聊天平台消息  │
└──────┬───────┘
       ↓
┌──────────────┐
│   Channel    │ ← 实现 BaseChannel
│  (Telegram)  │
└──────┬───────┘
       ↓ InboundMessage
┌──────────────┐
│ Message Bus  │
└──────┬───────┘
       ↓
┌──────────────┐
│ Agent Loop   │
└──────┬───────┘
       ↓ OutboundMessage
┌──────────────┐
│ Message Bus  │
└──────┬───────┘
       ↓
┌──────────────┐
│   Channel    │
└──────┬───────┘
       ↓
┌──────────────┐
│ 聊天平台消息  │
└──────────────┘
"""

from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus


class BaseChannel(ABC):
    """
    Channel 抽象基类

    所有聊天平台的 Channel 都必须继承这个类并实现其抽象方法。

    职责：
    1. 连接管理 - 连接到聊天平台并保持连接
    2. 消息接收 - 接收平台消息并转换为 InboundMessage
    3. 消息发送 - 将 OutboundMessage 发送到平台
    4. 访问控制 - 检查用户是否有权限使用 Bot

    实现要求：
    - 必须实现 start(), stop(), send() 方法
    - 使用 _handle_message() 转发接收到的消息
    - 使用 is_allowed() 检查访问权限

    使用示例：
    ```python
    class TelegramChannel(BaseChannel):
        name = "telegram"

        async def start(self):
            # 连接到 Telegram
            # 监听消息
            # 调用 _handle_message() 转发消息

        async def stop(self):
            # 断开连接
            # 清理资源

        async def send(self, msg: OutboundMessage):
            # 发送消息到 Telegram
    ```
    """

    # Channel 名称（子类必须设置）
    name: str = "base"

    def __init__(self, config: Any, bus: MessageBus):
        """
        初始化 Channel

        参数:
            config: Channel 特定的配置（如 TelegramConfig）
            bus: 消息总线（用于与 Agent 通信）
        """
        self.config = config
        self.bus = bus
        self._running = False  # 运行状态标志

    @abstractmethod
    async def start(self) -> None:
        """
        启动 Channel 并开始监听消息

        这是一个长时间运行的异步任务，应该：
        1. 连接到聊天平台
        2. 监听传入的消息
        3. 通过 _handle_message() 转发消息到总线

        实现注意事项：
        - 这个方法应该持续运行直到 stop() 被调用
        - 使用 self._running 标志控制循环
        - 处理连接错误和重连逻辑
        - 记录日志以便调试

        示例：
        ```python
        async def start(self):
            self._running = True
            while self._running:
                # 接收消息
                message = await platform.receive()
                # 转发到总线
                await self._handle_message(
                    sender_id=message.user_id,
                    chat_id=message.chat_id,
                    content=message.text
                )
        ```
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """
        停止 Channel 并清理资源

        应该：
        1. 设置 self._running = False
        2. 断开与平台的连接
        3. 清理资源（关闭文件、释放内存等）
        4. 等待正在处理的消息完成

        示例：
        ```python
        async def stop(self):
            self._running = False
            await self.platform.disconnect()
            logger.info(f"{self.name} channel stopped")
        ```
        """
        pass

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """
        发送消息到聊天平台

        这个方法将 OutboundMessage 转换为平台特定的格式并发送。

        参数:
            msg: 要发送的消息
                - channel: 目标 Channel（应该匹配 self.name）
                - chat_id: 目标聊天 ID
                - content: 消息内容
                - reply_to: 回复的消息 ID（可选）
                - media: 媒体文件 URL（可选）
                - metadata: 平台特定的元数据（可选）

        实现注意事项：
        - 检查 msg.channel 是否匹配 self.name
        - 处理 Markdown 格式转换（如果需要）
        - 处理媒体文件（图片、视频等）
        - 处理发送错误（重试、记录日志）
        - 考虑消息长度限制（分段发送）

        示例：
        ```python
        async def send(self, msg: OutboundMessage):
            if msg.channel != self.name:
                return

            try:
                await self.platform.send_message(
                    chat_id=msg.chat_id,
                    text=msg.content,
                    reply_to=msg.reply_to
                )
            except Exception as e:
                logger.error(f"Failed to send message: {e}")
        ```
        """
        pass

    def is_allowed(self, sender_id: str) -> bool:
        """
        检查发送者是否有权限使用 Bot

        访问控制逻辑：
        1. 如果没有配置 allowFrom，允许所有人
        2. 如果配置了 allowFrom，只允许白名单中的用户
        3. 支持复合 ID（用 | 分隔，如 "guild_id|user_id"）

        参数:
            sender_id: 发送者的唯一标识符

        返回:
            bool: True 表示允许，False 表示拒绝

        配置示例：
        ```json
        {
            "channels": {
                "telegram": {
                    "allowFrom": ["123456789", "987654321"]
                }
            }
        }
        ```

        复合 ID 示例（Discord）：
        - sender_id = "guild_123|user_456"
        - allowFrom = ["guild_123", "user_456"]
        - 任一部分匹配即允许
        """
        # 获取白名单（如果没有配置，返回空列表）
        allow_list = getattr(self.config, "allow_from", [])

        # 如果没有白名单，允许所有人
        if not allow_list:
            return True

        # 检查发送者 ID 是否在白名单中
        sender_str = str(sender_id)
        if sender_str in allow_list:
            return True

        # 检查复合 ID（如 "guild_id|user_id"）
        if "|" in sender_str:
            for part in sender_str.split("|"):
                if part and part in allow_list:
                    return True

        return False

    async def _handle_message(
        self,
        sender_id: str,
        chat_id: str,
        content: str,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """
        处理接收到的消息

        这是一个内部方法，由子类在接收到平台消息时调用。
        它负责：
        1. 检查访问权限
        2. 构建 InboundMessage
        3. 发布到消息总线

        参数:
            sender_id: 发送者的唯一标识符
            chat_id: 聊天/频道的唯一标识符
            content: 消息文本内容
            media: 媒体文件 URL 列表（可选）
            metadata: 平台特定的元数据（可选）
                例如：{"message_id": "123", "thread_ts": "456"}

        使用示例：
        ```python
        # 在子类的消息处理器中
        async def on_message(self, platform_message):
            await self._handle_message(
                sender_id=platform_message.user_id,
                chat_id=platform_message.chat_id,
                content=platform_message.text,
                media=platform_message.attachments,
                metadata={"message_id": platform_message.id}
            )
        ```

        访问控制：
        如果用户不在白名单中，会记录警告日志并拒绝消息。
        """
        # 检查访问权限
        if not self.is_allowed(sender_id):
            logger.warning(
                f"Access denied for sender {sender_id} on channel {self.name}. "
                f"Add them to allowFrom list in config to grant access."
            )
            return

        # 构建 InboundMessage
        msg = InboundMessage(
            channel=self.name,
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            content=content,
            media=media or [],
            metadata=metadata or {}
        )

        # 发布到消息总线
        await self.bus.publish_inbound(msg)

    @property
    def is_running(self) -> bool:
        """
        检查 Channel 是否正在运行

        返回:
            bool: True 表示正在运行，False 表示已停止
        """
        return self._running
