"""
LiteLLM Provider 实现 - 多 Provider 支持

这个模块实现了基于 LiteLLM 的 Provider。
LiteLLM 是一个统一的 LLM API 接口，支持 100+ LLM Provider。

核心功能：
1. 统一接口 - 所有 Provider 使用相同的 API
2. 自动路由 - 根据模型名自动选择 Provider
3. 前缀处理 - 自动添加 Provider 前缀
4. 环境变量 - 自动设置环境变量
5. 网关支持 - 支持 OpenRouter, AiHubMix 等网关

设计思路：
- 所有 Provider 逻辑由 registry.py 驱动
- 不需要 if-elif 链
- 易于扩展新 Provider

支持的 Provider：
- OpenRouter（网关）
- AiHubMix（网关）
- Anthropic（Claude）
- OpenAI（GPT）
- DeepSeek
- Gemini
- Zhipu（智谱）
- ... 更多（见 registry.py）
"""

import json
import os
from typing import Any

import litellm
from litellm import acompletion

from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from nanobot.providers.registry import find_by_model, find_gateway


class LiteLLMProvider(LLMProvider):
    """
    LiteLLM Provider 实现

    这是 nanobot 的主要 Provider 实现，使用 LiteLLM 库支持多个 LLM Provider。

    工作流程：
    1. 初始化时检测网关/本地部署
    2. 设置环境变量
    3. 调用 LLM 时解析模型名
    4. 应用模型特定的参数覆盖
    5. 调用 LiteLLM API
    6. 解析响应（文本或工具调用）

    Provider 特定逻辑：
    所有 Provider 特定的逻辑（前缀、环境变量等）都由 registry.py 驱动。
    这个类只负责调用 LiteLLM API 和处理响应。
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "anthropic/claude-opus-4-5",
        extra_headers: dict[str, str] | None = None,
        provider_name: str | None = None,
    ):
        """
        初始化 LiteLLM Provider

        参数:
            api_key: API 密钥
            api_base: API Base URL（用于自定义端点）
            default_model: 默认模型
            extra_headers: 额外的 HTTP 头（如 AiHubMix 的 APP-Code）
            provider_name: Provider 名称（来自配置，用于网关检测）
        """
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self.extra_headers = extra_headers or {}

        # 检测网关/本地部署
        # provider_name（来自配置键）是主要信号
        # api_key / api_base 是回退的自动检测
        self._gateway = find_gateway(provider_name, api_key, api_base)

        # 配置环境变量
        if api_key:
            self._setup_env(api_key, api_base, default_model)

        if api_base:
            litellm.api_base = api_base

        # 禁用 LiteLLM 的调试日志（太吵）
        litellm.suppress_debug_info = True
        # 丢弃不支持的参数（如 gpt-5 拒绝某些参数）
        litellm.drop_params = True

    def _setup_env(self, api_key: str, api_base: str | None, model: str) -> None:
        """
        根据检测到的 Provider 设置环境变量

        逻辑：
        1. 如果是网关，覆盖现有环境变量
        2. 如果是标准 Provider，使用 setdefault（不覆盖）
        3. 解析 env_extras 中的占位符

        参数:
            api_key: API 密钥
            api_base: API Base URL
            model: 模型名
        """
        # 查找 Provider 规范
        spec = self._gateway or find_by_model(model)
        if not spec:
            return

        # 网关/本地覆盖现有环境变量；标准 Provider 不覆盖
        if self._gateway:
            os.environ[spec.env_key] = api_key
        else:
            os.environ.setdefault(spec.env_key, api_key)

        # 解析 env_extras 占位符：
        #   {api_key}  → 用户的 API 密钥
        #   {api_base} → 用户的 api_base，回退到 spec.default_api_base
        effective_base = api_base or spec.default_api_base
        for env_name, env_val in spec.env_extras:
            resolved = env_val.replace("{api_key}", api_key)
            resolved = resolved.replace("{api_base}", effective_base)
            os.environ.setdefault(env_name, resolved)

    def _resolve_model(self, model: str) -> str:
        """
        解析模型名（应用 Provider/网关前缀）

        逻辑：
        1. 如果是网关模式：
           - 如果需要剥离前缀，剥离 "provider/" 部分
           - 应用网关前缀
        2. 如果是标准模式：
           - 查找 Provider
           - 如果需要前缀且模型名不在 skip_prefixes 中，添加前缀

        参数:
            model: 原始模型名

        返回:
            str: 解析后的模型名

        示例：
        # 网关模式（OpenRouter）
        "claude-opus-4-5" → "openrouter/claude-opus-4-5"

        # 网关模式（AiHubMix，strip_model_prefix=True）
        "anthropic/claude-opus-4-5" → "claude-opus-4-5" → "openai/claude-opus-4-5"

        # 标准模式（DeepSeek）
        "deepseek-chat" → "deepseek/deepseek-chat"

        # 标准模式（Anthropic，无前缀）
        "claude-opus-4-5" → "claude-opus-4-5"
        """
        if self._gateway:
            # 网关模式：应用网关前缀，跳过 Provider 特定前缀
            prefix = self._gateway.litellm_prefix
            if self._gateway.strip_model_prefix:
                # 剥离 "provider/" 部分（如 "anthropic/claude-3" → "claude-3"）
                model = model.split("/")[-1]
            if prefix and not model.startswith(f"{prefix}/"):
                model = f"{prefix}/{model}"
            return model

        # 标准模式：为已知 Provider 自动添加前缀
        spec = find_by_model(model)
        if spec and spec.litellm_prefix:
            # 如果模型名不在 skip_prefixes 中，添加前缀
            if not any(model.startswith(s) for s in spec.skip_prefixes):
                model = f"{spec.litellm_prefix}/{model}"

        return model

    def _apply_model_overrides(self, model: str, kwargs: dict[str, Any]) -> None:
        """
        应用模型特定的参数覆盖

        某些模型需要特定的参数设置。
        例如：kimi-k2.5 需要 temperature=1.0

        参数:
            model: 模型名
            kwargs: 要传递给 LiteLLM 的参数字典（会被修改）
        """
        model_lower = model.lower()
        spec = find_by_model(model)
        if spec:
            for pattern, overrides in spec.model_overrides:
                if pattern in model_lower:
                    kwargs.update(overrides)
                    return

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        发送聊天完成请求

        这是 Provider 的核心方法，负责：
        1. 解析模型名
        2. 构建请求参数
        3. 应用模型特定覆盖
        4. 调用 LiteLLM API
        5. 解析响应

        参数:
            messages: 消息列表（OpenAI 格式）
                [
                    {"role": "system", "content": "..."},
                    {"role": "user", "content": "..."},
                    {"role": "assistant", "content": "..."}
                ]
            tools: 工具定义列表（OpenAI Function Calling 格式）
            model: 模型标识符（如 "anthropic/claude-sonnet-4-5"）
            max_tokens: 最大 token 数
            temperature: 采样温度（0-2）

        返回:
            LLMResponse: 包含内容和/或工具调用的响应

        工具调用流程：
        1. LLM 返回工具调用请求
        2. Agent 执行工具
        3. 将结果添加到消息列表
        4. 再次调用 LLM（LLM 根据工具结果继续思考）
        """
        # 1. 解析模型名（应用前缀）
        model = self._resolve_model(model or self.default_model)

        # 2. 构建请求参数
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # 3. 应用模型特定覆盖（如 kimi-k2.5 的 temperature）
        self._apply_model_overrides(model, kwargs)

        # 4. 传递 API 密钥（比仅依赖环境变量更可靠）
        if self.api_key:
            kwargs["api_key"] = self.api_key

        # 5. 传递 API Base（用于自定义端点）
        if self.api_base:
            kwargs["api_base"] = self.api_base

        # 6. 传递额外的 HTTP 头（如 AiHubMix 的 APP-Code）
        if self.extra_headers:
            kwargs["extra_headers"] = self.extra_headers

        # 7. 如果有工具，添加工具定义
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"  # 让 LLM 自动决定是否调用工具

        # 8. 调用 LiteLLM API（异步）
        response = await acompletion(**kwargs)

        # 9. 解析响应
        return self._parse_response(response)

    def _parse_response(self, response: Any) -> LLMResponse:
        """
        解析 LiteLLM 响应

        LiteLLM 返回的响应格式：
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "文本内容",
                        "tool_calls": [...]  # 如果有工具调用
                    }
                }
            ]
        }

        参数:
            response: LiteLLM 响应对象

        返回:
            LLMResponse: 标准化的响应对象
        """
        choice = response.choices[0]
        message = choice.message

        # 提取文本内容
        content = message.content or ""

        # 提取工具调用
        tool_calls = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                # 解析工具调用参数（JSON 字符串）
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=arguments
                ))

        # 提取思考内容（DeepSeek-R1, Kimi 等思考模型）
        reasoning_content = None
        if hasattr(message, "reasoning_content"):
            reasoning_content = message.reasoning_content

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            reasoning_content=reasoning_content
        )

    def get_default_model(self) -> str:
        """
        获取默认模型

        返回:
            str: 默认模型名
        """
        return self.default_model
