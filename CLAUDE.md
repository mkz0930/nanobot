# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

nanobot 是一个超轻量级的个人 AI 助手框架，核心代码仅约 4,000 行。它使用 Python 3.11+ 开发，基于 LiteLLM 支持多种 LLM 提供商，并通过多个聊天平台（Telegram、Discord、WhatsApp、Feishu、Slack 等）提供服务。

## Development Commands

### Setup & Installation
```bash
# 从源码安装（开发模式）
pip install -e .

# 安装开发依赖
pip install -e ".[dev]"
```

### Testing
```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_tool_validation.py

# 异步测试自动启用（见 pyproject.toml 的 asyncio_mode = "auto"）
```

### Code Quality
```bash
# 代码格式检查和修复（使用 ruff）
ruff check .
ruff check --fix .

# 格式化代码
ruff format .
```

### Running the Agent
```bash
# 初始化配置
nanobot onboard

# 单次对话
nanobot agent -m "你的消息"

# 交互模式
nanobot agent

# 启动网关（连接聊天平台）
nanobot gateway

# 查看状态
nanobot status
```

### Docker
```bash
# 构建镜像
docker build -t nanobot .

# 初始化配置
docker run -v ~/.nanobot:/root/.nanobot --rm nanobot onboard

# 运行网关
docker run -v ~/.nanobot:/root/.nanobot -p 18790:18790 nanobot gateway
```

## Architecture

### Core Components

**Agent Loop** (`nanobot/agent/loop.py`)
- 核心处理引擎，负责消息接收、上下文构建、LLM 调用、工具执行和响应发送
- 使用 `ContextBuilder` 构建包含历史、记忆和技能的上下文
- 通过 `ToolRegistry` 管理所有可用工具
- 支持 `SubagentManager` 用于后台任务执行

**Tools System** (`nanobot/agent/tools/`)
- 所有工具继承自 `Tool` 基类（`base.py`）
- 工具必须实现：`name`、`description`、`parameters`（JSON Schema）、`execute()` 方法
- 内置工具包括：文件操作、Shell 执行、Web 搜索/抓取、消息发送、Spawn（子代理）、Cron（定时任务）
- 工具参数通过 JSON Schema 验证（`validate_params` 方法）

**Provider System** (`nanobot/providers/`)
- 使用 **Provider Registry** 模式（`registry.py`）作为单一数据源
- 添加新 Provider 只需 2 步：
  1. 在 `registry.py` 的 `PROVIDERS` 中添加 `ProviderSpec`
  2. 在 `config/schema.py` 的 `ProvidersConfig` 中添加字段
- 自动处理环境变量、模型前缀、配置匹配和状态显示

**Message Bus** (`nanobot/bus/`)
- 使用事件驱动架构（`events.py`）处理 `InboundMessage` 和 `OutboundMessage`
- `MessageBus`（`queue.py`）负责消息路由和分发

**Channels** (`nanobot/channels/`)
- 每个聊天平台一个独立模块（`telegram.py`、`discord.py` 等）
- 所有 Channel 继承自 `BaseChannel`（`base.py`）
- 支持 WebSocket 长连接（Feishu、Mochat、DingTalk）和轮询模式（Email）

**Skills** (`nanobot/skills/`)
- 技能是可加载的 Markdown 文档，为 Agent 提供专业知识
- 每个技能目录包含 `SKILL.md` 文件
- 通过 `SkillsLoader`（`agent/skills.py`）动态加载

**Session Management** (`nanobot/session/`)
- 管理多用户对话历史和上下文
- 支持持久化存储

**Configuration** (`nanobot/config/`)
- 使用 Pydantic 进行配置验证（`schema.py`）
- 配置文件位于 `~/.nanobot/config.json`
- 支持多 Provider、多 Channel 配置

### Key Design Patterns

1. **工具注册模式**：所有工具通过 `ToolRegistry` 注册，Agent 动态调用
2. **Provider Registry**：集中管理 LLM Provider 元数据，避免 if-elif 链
3. **事件驱动**：消息通过 Bus 异步传递，解耦 Channel 和 Agent
4. **沙箱模式**：`restrict_to_workspace=True` 时，所有文件和 Shell 工具限制在工作区内

## Important Notes

### Security
- 生产环境应设置 `tools.restrictToWorkspace: true` 以启用沙箱
- 使用 `channels.*.allowFrom` 白名单限制用户访问
- 工具执行前会进行参数验证（JSON Schema）

### Adding New Providers
参考 `nanobot/providers/registry.py` 顶部的注释。关键字段：
- `litellm_prefix`：自动为模型名添加前缀
- `skip_prefixes`：避免重复前缀
- `is_gateway`：标记为网关（如 OpenRouter）
- `model_overrides`：针对特定模型的参数覆盖

### Adding New Tools
1. 继承 `Tool` 基类
2. 实现必需的属性和方法
3. 在 `AgentLoop._register_default_tools()` 中注册
4. 工具应返回字符串结果

### Testing
- 使用 pytest 进行测试
- 异步测试自动处理（`asyncio_mode = "auto"`）
- 测试文件位于 `tests/` 目录

### WhatsApp Bridge
- WhatsApp 支持需要 Node.js ≥18
- Bridge 代码位于 `bridge/` 目录（TypeScript）
- 使用 `nanobot channels login` 扫码登录

## Configuration Location

- 配置文件：`~/.nanobot/config.json`
- 工作区：`~/.nanobot/workspace/`
- 会话数据：`~/.nanobot/sessions/`

## Code Style

- 使用 ruff 进行代码检查和格式化
- 行长度限制：100 字符
- 目标 Python 版本：3.11
- 忽略 E501（行长度）错误
