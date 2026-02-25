"""
上下文构建器 - 组装 Agent 的完整上下文

这个模块负责构建 Agent 的系统提示和消息列表。
它将多个来源的信息组合成一个完整的上下文：
1. 核心身份 - Agent 的基本信息和能力
2. 引导文件 - AGENTS.md, SOUL.md, USER.md 等用户自定义文件
3. 记忆上下文 - 从 memory/MEMORY.md 加载的长期记忆
4. 技能摘要 - 可用技能列表（渐进式加载）

设计思路：
- 使用渐进式加载策略节省 token
- Always-loaded skills 完整加载，其他技能仅显示摘要
- Agent 可以按需使用 read_file 工具加载完整技能内容
"""

import base64
import mimetypes
import platform
from pathlib import Path
from typing import Any

from nanobot.agent.memory import MemoryStore
from nanobot.agent.skills import SkillsLoader


class ContextBuilder:
    """
    上下文构建器 - Agent 的上下文组装工厂

    职责：
    1. 构建系统提示（system prompt）
    2. 组装消息列表（包含历史和当前消息）
    3. 管理技能的渐进式加载
    4. 处理多模态内容（文本 + 图片）

    使用场景：
    - Agent Loop 在处理每条消息时调用
    - 需要构建完整的 LLM 输入上下文
    """

    # 引导文件列表 - 这些文件如果存在会被自动加载到系统提示中
    # 用户可以在工作区创建这些文件来自定义 Agent 行为
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]

    def __init__(self, workspace: Path):
        """
        初始化上下文构建器

        参数:
            workspace: 工作区路径（~/.nanobot/workspace/）
        """
        self.workspace = workspace
        # 记忆存储 - 管理长期记忆（MEMORY.md 和日记）
        self.memory = MemoryStore(workspace)
        # 技能加载器 - 管理技能的发现和加载
        self.skills = SkillsLoader(workspace)

    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        """
        构建系统提示（System Prompt）

        系统提示是 Agent 的"操作手册"，包含：
        1. 核心身份 - 你是谁，能做什么
        2. 引导文件 - 用户自定义的行为规则
        3. 记忆上下文 - 长期记忆内容
        4. 技能摘要 - 可用的技能列表

        参数:
            skill_names: 可选的技能名称列表（当前未使用）

        返回:
            str: 完整的系统提示文本
        """
        parts = []

        # 1. 核心身份 - Agent 的基本信息
        parts.append(self._get_identity())

        # 2. 引导文件 - 用户自定义的配置文件
        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)

        # 3. 记忆上下文 - 长期记忆
        memory = self.memory.get_memory_context()
        if memory:
            parts.append(f"# Memory\n\n{memory}")

        # 4. 技能系统 - 渐进式加载
        # 4.1 Always-loaded skills: 完整内容加载到上下文
        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")

        # 4.2 Available skills: 仅显示摘要，Agent 按需使用 read_file 加载
        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""")

        # 使用分隔符连接所有部分
        return "\n\n---\n\n".join(parts)

    def _get_identity(self) -> str:
        """
        获取核心身份部分

        这是 Agent 的"自我介绍"，包含：
        - 名称和基本能力
        - 当前时间和运行环境
        - 工作区路径
        - 使用工具的基本规则

        返回:
            str: 核心身份文本
        """
        from datetime import datetime

        # 获取当前时间（格式：2024-01-15 14:30 (Monday)）
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")

        # 获取工作区的绝对路径
        workspace_path = str(self.workspace.expanduser().resolve())

        # 获取操作系统信息
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"

        return f"""# nanobot 🐈

You are nanobot, a helpful AI assistant. You have access to tools that allow you to:
- Read, write, and edit files
- Execute shell commands
- Search the web and fetch web pages
- Send messages to users on chat channels
- Spawn subagents for complex background tasks

## Current Time
{now}

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}
- Memory files: {workspace_path}/memory/MEMORY.md
- Daily notes: {workspace_path}/memory/YYYY-MM-DD.md
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md

IMPORTANT: When responding to direct questions or conversations, reply directly with your text response.
Only use the 'message' tool when you need to send a message to a specific chat channel (like WhatsApp).
For normal conversation, just respond with text - do not call the message tool.

Always be helpful, accurate, and concise. When using tools, explain what you're doing.
When remembering something, write to {workspace_path}/memory/MEMORY.md"""

    def _load_bootstrap_files(self) -> str:
        """
        加载所有引导文件

        引导文件是用户在工作区创建的 Markdown 文件，用于自定义 Agent 行为。
        例如：
        - AGENTS.md: 定义多个 Agent 的角色和职责
        - SOUL.md: 定义 Agent 的性格和风格
        - USER.md: 用户的个人信息和偏好
        - TOOLS.md: 工具使用的额外说明
        - IDENTITY.md: 自定义身份信息

        返回:
            str: 所有引导文件的内容（如果存在）
        """
        parts = []

        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")

        return "\n\n".join(parts) if parts else ""

    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        构建完整的消息列表

        这个方法组装 LLM 调用所需的完整消息列表，包括：
        1. 系统提示（system message）
        2. 历史消息（user 和 assistant 的对话历史）
        3. 当前消息（新的 user 消息）

        消息格式遵循 OpenAI Chat Completion API 标准：
        [
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "用户消息1"},
            {"role": "assistant", "content": "助手回复1"},
            {"role": "user", "content": "用户消息2"}
        ]

        参数:
            history: 历史消息列表（从 SessionManager 获取）
            current_message: 当前用户消息
            skill_names: 可选的技能列表
            media: 可选的媒体文件路径列表（图片等）
            channel: 当前聊天平台（telegram, discord 等）
            chat_id: 当前聊天 ID

        返回:
            list[dict[str, Any]]: 完整的消息列表
        """
        messages = []

        # 1. 系统提示
        system_prompt = self.build_system_prompt(skill_names)
        # 添加当前会话信息（用于上下文感知）
        if channel and chat_id:
            system_prompt += f"\n\n## Current Session\nChannel: {channel}\nChat ID: {chat_id}"
        messages.append({"role": "system", "content": system_prompt})

        # 2. 历史消息
        messages.extend(history)

        # 3. 当前消息（可能包含图片）
        user_content = self._build_user_content(current_message, media)
        messages.append({"role": "user", "content": user_content})

        return messages

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """
        构建用户消息内容（支持多模态）

        如果有图片，将图片转换为 base64 编码并嵌入消息中。
        这样 LLM 可以"看到"图片内容（如果支持视觉能力）。

        参数:
            text: 文本内容
            media: 媒体文件路径列表

        返回:
            str | list[dict]: 纯文本或多模态内容列表
        """
        if not media:
            return text

        images = []
        for path in media:
            p = Path(path)
            # 猜测 MIME 类型（image/png, image/jpeg 等）
            mime, _ = mimetypes.guess_type(path)
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue
            # 读取文件并转换为 base64
            b64 = base64.b64encode(p.read_bytes()).decode()
            # 构建 data URL
            images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

        if not images:
            return text
        # 多模态格式：[图片1, 图片2, 文本]
        return images + [{"type": "text", "text": text}]

    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str
    ) -> list[dict[str, Any]]:
        """
        添加工具执行结果到消息列表

        工具调用流程：
        1. LLM 返回工具调用请求（tool_calls）
        2. Agent 执行工具
        3. 使用此方法将结果添加到消息列表
        4. 继续调用 LLM（LLM 会根据工具结果继续思考）

        参数:
            messages: 当前消息列表
            tool_call_id: 工具调用的唯一 ID
            tool_name: 工具名称
            result: 工具执行结果（字符串）

        返回:
            list[dict[str, Any]]: 更新后的消息列表
        """
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result
        })
        return messages

    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        添加助手消息到消息列表

        助手消息可能包含：
        - 纯文本回复
        - 工具调用请求
        - 思考过程（reasoning_content，用于 DeepSeek-R1 等思考模型）

        参数:
            messages: 当前消息列表
            content: 消息内容
            tool_calls: 工具调用列表（如果 LLM 要调用工具）
            reasoning_content: 思考过程（某些模型支持）

        返回:
            list[dict[str, Any]]: 更新后的消息列表
        """
        msg: dict[str, Any] = {"role": "assistant", "content": content or ""}

        if tool_calls:
            msg["tool_calls"] = tool_calls

        # 思考模型（如 Kimi, DeepSeek-R1）需要保留 reasoning_content
        # 否则在历史记录中会被拒绝
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content

        messages.append(msg)
        return messages
