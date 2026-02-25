"""
消息总线 - 异步消息队列系统

这个模块实现了 nanobot 的消息总线（Message Bus）。
消息总线是事件驱动架构的核心，负责解耦 Channel 和 Agent。

核心设计模式：发布-订阅模式（Pub-Sub Pattern）

优势：
1. 解耦组件 - Channel 和 Agent 不直接通信
2. 异步处理 - 使用 asyncio.Queue 实现异步消息传递
3. 易于扩展 - 可以轻松添加新的 Channel 或 Agent
4. 可靠性 - 消息队列保证消息不丢失

消息流程：
┌─────────────┐
│  Channel 1  │ ──┐
└─────────────┘   │
                  ├─> InboundMessage ──> [Inbound Queue]
┌─────────────┐   │                            ↓
│  Channel 2  │ ──┘                      ┌──────────┐
└─────────────┘                          │  Agent   │
                                         └──────────┘
┌─────────────┐                                ↓
│  Channel 1  │ <─┐                   [Outbound Queue]
└─────────────┘   │                            ↓
                  ├── OutboundMessage <── Dispatcher
┌─────────────┐   │
│  Channel 2  │ <─┘
└─────────────┘

工作原理：
1. Channel 接收平台消息，发布 InboundMessage 到总线
2. Agent 从总线消费 InboundMessage，处理后发布 OutboundMessage
3. Dispatcher 从总线消费 OutboundMessage，分发给对应的 Channel
4. Channel 将消息发送到聊天平台
"""

import asyncio
from typing import Callable, Awaitable

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage


class MessageBus:
    """
    异步消息总线

    职责：
    1. 消息队列 - 管理入站和出站消息队列
    2. 发布-订阅 - 支持 Channel 订阅出站消息
    3. 消息分发 - 将出站消息分发给对应的 Channel
    4. 解耦组件 - Channel 和 Agent 通过总线通信

    核心组件：
    - inbound: 入站消息队列（Channel → Agent）
    - outbound: 出站消息队列（Agent → Channel）
    - _outbound_subscribers: 出站消息订阅者（Channel 的回调函数）

    使用场景：
    - Gateway 启动时创建 MessageBus
    - 所有 Channel 和 Agent 共享同一个 MessageBus
    - Channel 订阅出站消息以接收响应
    """

    def __init__(self):
        """
        初始化消息总线

        创建两个异步队列：
        - inbound: 入站消息队列（无限大小）
        - outbound: 出站消息队列（无限大小）

        订阅者字典：
        - key: channel 名称（如 "telegram", "discord"）
        - value: 回调函数列表（接收 OutboundMessage）
        """
        # 入站消息队列（Channel → Agent）
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()

        # 出站消息队列（Agent → Channel）
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()

        # 出站消息订阅者（Channel 的回调函数）
        # 格式：{"telegram": [callback1, callback2], "discord": [callback3]}
        self._outbound_subscribers: dict[str, list[Callable[[OutboundMessage], Awaitable[None]]]] = {}

        # 运行状态标志
        self._running = False

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """
        发布入站消息（Channel → Agent）

        Channel 接收到平台消息后，调用此方法将消息发布到总线。
        Agent 会从队列中消费这些消息。

        参数:
            msg: 入站消息（包含 channel, sender_id, chat_id, content 等）

        使用示例：
        ```python
        # 在 Channel 中
        msg = InboundMessage(
            channel="telegram",
            sender_id="123456",
            chat_id="789",
            content="Hello"
        )
        await bus.publish_inbound(msg)
        ```

        注意：
        - 这是一个异步操作，但通常不会阻塞（队列无限大）
        - 消息会按照发布顺序排队
        """
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        """
        消费入站消息（Agent 使用）

        Agent 调用此方法从队列中获取下一条消息。
        如果队列为空，会阻塞等待直到有新消息。

        返回:
            InboundMessage: 下一条入站消息

        使用示例：
        ```python
        # 在 Agent Loop 中
        while running:
            msg = await bus.consume_inbound()
            response = await process_message(msg)
            await bus.publish_outbound(response)
        ```

        注意：
        - 这是一个阻塞操作，会等待直到有消息可用
        - 通常配合超时使用（见 Agent Loop 的实现）
        """
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """
        发布出站消息（Agent → Channel）

        Agent 处理完消息后，调用此方法将响应发布到总线。
        Dispatcher 会将消息分发给对应的 Channel。

        参数:
            msg: 出站消息（包含 channel, chat_id, content 等）

        使用示例：
        ```python
        # 在 Agent 中
        response = OutboundMessage(
            channel="telegram",
            chat_id="789",
            content="Hello! How can I help?"
        )
        await bus.publish_outbound(response)
        ```

        注意：
        - 消息会被放入队列，由 Dispatcher 异步分发
        - 如果没有订阅者，消息会被丢弃（记录错误日志）
        """
        await self.outbound.put(msg)

    async def consume_outbound(self) -> OutboundMessage:
        """
        消费出站消息（Dispatcher 使用）

        Dispatcher 调用此方法从队列中获取下一条消息。
        如果队列为空，会阻塞等待直到有新消息。

        返回:
            OutboundMessage: 下一条出站消息

        注意：
        - 这个方法通常不直接使用
        - 推荐使用 dispatch_outbound() 自动分发消息
        """
        return await self.outbound.get()

    def subscribe_outbound(
        self,
        channel: str,
        callback: Callable[[OutboundMessage], Awaitable[None]]
    ) -> None:
        """
        订阅出站消息（Channel 使用）

        Channel 启动时调用此方法订阅出站消息。
        当有发往该 Channel 的消息时，会调用回调函数。

        参数:
            channel: Channel 名称（如 "telegram", "discord"）
            callback: 异步回调函数，接收 OutboundMessage

        使用示例：
        ```python
        # 在 Channel 中
        class TelegramChannel(BaseChannel):
            async def start(self):
                # 订阅出站消息
                self.bus.subscribe_outbound("telegram", self.send)

            async def send(self, msg: OutboundMessage):
                # 发送消息到 Telegram
                await telegram_api.send_message(msg.chat_id, msg.content)
        ```

        注意：
        - 一个 Channel 可以有多个订阅者（通常只有一个）
        - 回调函数必须是异步的
        - 回调函数中的异常会被捕获并记录日志
        """
        if channel not in self._outbound_subscribers:
            self._outbound_subscribers[channel] = []
        self._outbound_subscribers[channel].append(callback)

    async def dispatch_outbound(self) -> None:
        """
        分发出站消息（后台任务）

        这是一个长时间运行的后台任务，负责：
        1. 从出站队列获取消息
        2. 查找订阅该 Channel 的回调函数
        3. 调用所有回调函数分发消息

        工作流程：
        ```
        1. 等待出站消息（1 秒超时）
        2. 如果有消息：
           a. 查找订阅者
           b. 调用所有回调函数
           c. 捕获并记录异常
        3. 如果超时：继续循环
        4. 重复直到 stop() 被调用
        ```

        使用示例：
        ```python
        # 在 Gateway 中
        bus = MessageBus()
        # 启动分发器（后台任务）
        asyncio.create_task(bus.dispatch_outbound())
        ```

        错误处理：
        - 如果回调函数抛出异常，会记录错误日志但不会中断循环
        - 这确保一个 Channel 的错误不会影响其他 Channel
        """
        self._running = True
        while self._running:
            try:
                # 等待下一条出站消息（1 秒超时）
                msg = await asyncio.wait_for(self.outbound.get(), timeout=1.0)

                # 查找订阅该 Channel 的回调函数
                subscribers = self._outbound_subscribers.get(msg.channel, [])

                # 调用所有订阅者
                for callback in subscribers:
                    try:
                        await callback(msg)
                    except Exception as e:
                        # 捕获异常，避免影响其他订阅者
                        logger.error(f"Error dispatching to {msg.channel}: {e}")

            except asyncio.TimeoutError:
                # 超时，继续循环
                continue

    def stop(self) -> None:
        """
        停止分发器

        设置运行标志为 False，dispatch_outbound() 会在下一次循环时退出。

        使用示例：
        ```python
        # 在 Gateway 关闭时
        bus.stop()
        ```
        """
        self._running = False

    @property
    def inbound_size(self) -> int:
        """
        获取入站队列大小

        返回:
            int: 待处理的入站消息数量

        用途：
        - 监控队列积压情况
        - 调试和性能分析
        """
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        """
        获取出站队列大小

        返回:
            int: 待分发的出站消息数量

        用途：
        - 监控队列积压情况
        - 调试和性能分析
        """
        return self.outbound.qsize()
