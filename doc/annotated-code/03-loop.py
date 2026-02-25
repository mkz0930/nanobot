"""
Agent 主循环 - nanobot 的核心处理引擎

这是 nanobot 最核心的模块，负责：
1. 接收来自消息总线的消息
2. 构建完整的上下文（系统提示 + 历史 + 记忆 + 技能）
3. 调用 LLM 获取响应
4. 执行工具调用
5. 管理多轮对话循环
6. 发送响应回消息总线

核心流程：
┌─────────────┐
│ Message Bus │ ──> InboundMessage
└─────────────┘
       │
       ↓
┌─────────────┐
│ Agent Loop  │
│             │
│ 1. 加载会话 │
│ 2. 构建上下文│
│ 3. 调用 LLM │
│ 4. 执行工具 │
│ 5. 保存会话 │
└─────────────┘
       │
       ↓
┌─────────────┐
│ Message Bus │ <── OutboundMessage
└─────────────┘

设计模式：
- 事件驱动：通过消息总线解耦
- 工具注册表：统一管理所有工具
- 会话管理：支持多用户并发对话
- 子代理：支持后台任务执行
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.agent.context import ContextBuilder
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebSearchTool, WebFetchTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.subagent import SubagentManager
from nanobot.session.manager import SessionManager


class AgentLoop:
    """
    Agent 主循环 - nanobot 的大脑

    职责：
    1. 消息处理 - 接收和处理来自各个聊天平台的消息
    2. 上下文管理 - 构建包含历史、记忆、技能的完整上下文
    3. LLM 交互 - 调用 LLM 并处理响应
    4. 工具执行 - 执行 LLM 请求的工具调用
    5. 会话管理 - 管理多用户的对话历史
    6. 子代理管理 - 支持后台任务执行

    工作流程：
    1. 从消息总线接收 InboundMessage
    2. 加载对应会话的历史记录
    3. 构建完整上下文（系统提示 + 历史 + 当前消息）
    4. 进入 Agent 循环：
       a. 调用 LLM
       b. 如果有工具调用，执行工具并继续循环
       c. 如果没有工具调用，返回文本响应
    5. 保存会话历史
    6. 发送 OutboundMessage 到消息总线
    """

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 20,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        cron_service: "CronService | None" = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
    ):
        """
        初始化 Agent Loop

        参数:
            bus: 消息总线（用于接收和发送消息）
            provider: LLM 提供商（OpenAI, Anthropic 等）
            workspace: 工作区路径（~/.nanobot/workspace/）
            model: 模型名称（如果不指定，使用 provider 的默认模型）
            max_iterations: 最大迭代次数（防止无限循环）
            brave_api_key: Brave Search API 密钥（用于 Web 搜索）
            exec_config: Shell 执行配置（超时、环境变量等）
            cron_service: 定时任务服务
            restrict_to_workspace: 是否启用沙箱模式（限制文件和命令访问）
            session_manager: 会话管理器（如果不指定，创建新的）
        """
        from nanobot.config.schema import ExecToolConfig
        from nanobot.cron.service import CronService

        # 核心组件
        self.bus = bus  # 消息总线
        self.provider = provider  # LLM 提供商
        self.workspace = workspace  # 工作区路径
        self.model = model or provider.get_default_model()  # 使用的模型
        self.max_iterations = max_iterations  # 最大迭代次数
        self.brave_api_key = brave_api_key  # Web 搜索 API 密钥
        self.exec_config = exec_config or ExecToolConfig()  # Shell 执行配置
        self.cron_service = cron_service  # 定时任务服务
        self.restrict_to_workspace = restrict_to_workspace  # 沙箱模式

        # 上下文构建器 - 负责组装系统提示和消息列表
        self.context = ContextBuilder(workspace)

        # 会话管理器 - 管理多用户的对话历史
        self.sessions = session_manager or SessionManager(workspace)

        # 工具注册表 - 管理所有可用工具
        self.tools = ToolRegistry()

        # 子代理管理器 - 管理后台任务
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            brave_api_key=brave_api_key,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )

        self._running = False  # 运行状态标志
        self._register_default_tools()  # 注册默认工具

    def _register_default_tools(self) -> None:
        """
        注册默认工具集

        nanobot 内置的工具包括：
        1. 文件工具 - 读写编辑文件
        2. Shell 工具 - 执行命令
        3. Web 工具 - 搜索和抓取网页
        4. 消息工具 - 发送消息到聊天平台
        5. Spawn 工具 - 创建子代理
        6. Cron 工具 - 定时任务

        沙箱模式：
        如果 restrict_to_workspace=True，文件和 Shell 工具会被限制在工作区内
        """
        # 文件工具（如果启用沙箱，限制在工作区内）
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        self.tools.register(ReadFileTool(allowed_dir=allowed_dir))
        self.tools.register(WriteFileTool(allowed_dir=allowed_dir))
        self.tools.register(EditFileTool(allowed_dir=allowed_dir))
        self.tools.register(ListDirTool(allowed_dir=allowed_dir))

        # Shell 工具
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),
            timeout=self.exec_config.timeout,
            restrict_to_workspace=self.restrict_to_workspace,
        ))

        # Web 工具
        self.tools.register(WebSearchTool(api_key=self.brave_api_key))
        self.tools.register(WebFetchTool())

        # 消息工具（用于发送消息到聊天平台）
        message_tool = MessageTool(send_callback=self.bus.publish_outbound)
        self.tools.register(message_tool)

        # Spawn 工具（用于创建子代理）
        spawn_tool = SpawnTool(manager=self.subagents)
        self.tools.register(spawn_tool)

        # Cron 工具（用于定时任务）
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

    async def run(self) -> None:
        """
        运行 Agent 循环

        这是 Agent 的主事件循环，持续运行直到调用 stop()。
        循环流程：
        1. 从消息总线等待新消息（1 秒超时）
        2. 处理消息
        3. 发送响应
        4. 如果出错，发送错误消息
        5. 继续循环
        """
        self._running = True
        logger.info("Agent loop started")

        while self._running:
            try:
                # 等待下一条消息（1 秒超时）
                msg = await asyncio.wait_for(
                    self.bus.consume_inbound(),
                    timeout=1.0
                )

                # 处理消息
                try:
                    response = await self._process_message(msg)
                    if response:
                        await self.bus.publish_outbound(response)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    # 发送错误响应
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=f"Sorry, I encountered an error: {str(e)}"
                    ))
            except asyncio.TimeoutError:
                # 超时，继续循环
                continue

    def stop(self) -> None:
        """停止 Agent 循环"""
        self._running = False
        logger.info("Agent loop stopping")

    async def _process_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        处理单条消息

        这是消息处理的核心方法，包含完整的 Agent 循环逻辑。

        流程：
        1. 加载会话历史
        2. 更新工具上下文（设置当前 channel 和 chat_id）
        3. 构建消息列表（系统提示 + 历史 + 当前消息）
        4. 进入 Agent 循环：
           - 调用 LLM
           - 如果有工具调用，执行工具并继续
           - 如果没有工具调用，返回文本响应
        5. 保存会话历史
        6. 返回响应消息

        参数:
            msg: 接收到的消息

        返回:
            OutboundMessage | None: 响应消息（如果需要）
        """
        # 处理系统消息（子代理通知）
        if msg.channel == "system":
            return await self._process_system_message(msg)

        # 记录消息预览
        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info(f"Processing message from {msg.channel}:{msg.sender_id}: {preview}")

        # 1. 获取或创建会话
        session = self.sessions.get_or_create(msg.session_key)

        # 2. 更新工具上下文（让工具知道当前的 channel 和 chat_id）
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(msg.channel, msg.chat_id)

        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(msg.channel, msg.chat_id)

        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(msg.channel, msg.chat_id)

        # 3. 构建初始消息列表
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
        )

        # 4. Agent 循环 - 核心处理逻辑
        iteration = 0
        final_content = None

        while iteration < self.max_iterations:
            iteration += 1

            # 调用 LLM
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model
            )

            # 处理工具调用
            if response.has_tool_calls:
                # 添加助手消息（包含工具调用）
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)  # 必须是 JSON 字符串
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )

                # 执行所有工具调用
                for tool_call in response.tool_calls:
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                # 没有工具调用，循环结束
                final_content = response.content
                break

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        # 记录响应预览
        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info(f"Response to {msg.channel}:{msg.sender_id}: {preview}")

        # 5. 保存到会话
        session.add_message("user", msg.content)
        session.add_message("assistant", final_content)
        self.sessions.save(session)

        # 6. 返回响应
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata=msg.metadata or {},  # 传递元数据（如 Slack 的 thread_ts）
        )

    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        处理系统消息（如子代理通知）

        系统消息的特点：
        - channel = "system"
        - chat_id 包含原始的 "channel:chat_id"（用于路由响应）
        - 用于子代理完成任务后通知主 Agent

        参数:
            msg: 系统消息

        返回:
            OutboundMessage | None: 响应消息
        """
        logger.info(f"Processing system message from {msg.sender_id}")

        # 解析原始来源（格式：channel:chat_id）
        if ":" in msg.chat_id:
            parts = msg.chat_id.split(":", 1)
            origin_channel = parts[0]
            origin_chat_id = parts[1]
        else:
            # 回退
            origin_channel = "cli"
            origin_chat_id = msg.chat_id

        # 使用原始会话的上下文
        session_key = f"{origin_channel}:{origin_chat_id}"
        session = self.sessions.get_or_create(session_key)

        # 更新工具上下文
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(origin_channel, origin_chat_id)

        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(origin_channel, origin_chat_id)

        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(origin_channel, origin_chat_id)

        # 构建消息列表
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content,
            channel=origin_channel,
            chat_id=origin_chat_id,
        )

        # Agent 循环（限制迭代次数）
        iteration = 0
        final_content = None

        while iteration < self.max_iterations:
            iteration += 1

            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model
            )

            if response.has_tool_calls:
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )

                for tool_call in response.tool_calls:
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                final_content = response.content
                break

        if final_content is None:
            final_content = "Background task completed."

        # 保存到会话（标记为系统消息）
        session.add_message("user", f"[System: {msg.sender_id}] {msg.content}")
        session.add_message("assistant", final_content)
        self.sessions.save(session)

        return OutboundMessage(
            channel=origin_channel,
            chat_id=origin_chat_id,
            content=final_content
        )

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
    ) -> str:
        """
        直接处理消息（用于 CLI 或 Cron）

        这个方法绕过消息总线，直接处理消息并返回响应。
        主要用于：
        - CLI 交互模式
        - 定时任务执行

        参数:
            content: 消息内容
            session_key: 会话标识符
            channel: 来源平台（用于上下文）
            chat_id: 聊天 ID（用于上下文）

        返回:
            str: Agent 的响应
        """
        msg = InboundMessage(
            channel=channel,
            sender_id="user",
            chat_id=chat_id,
            content=content
        )

        response = await self._process_message(msg)
        return response.content if response else ""
