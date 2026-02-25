"""
Provider 注册表 - LLM Provider 元数据的单一数据源

这是 nanobot Provider 系统的核心设计。
所有 Provider 的元数据集中在这里管理，避免在代码中硬编码 if-elif 链。

核心设计模式：Provider Registry Pattern

优势：
1. 单一数据源 - 所有 Provider 信息集中管理
2. 易于扩展 - 添加新 Provider 只需添加一个 ProviderSpec
3. 自动处理 - 自动设置环境变量、模型前缀等
4. 避免 if-elif - 不需要硬编码的条件判断

添加新 Provider 的步骤：
1. 在 PROVIDERS 中添加一个 ProviderSpec
2. 在 config/schema.py 的 ProvidersConfig 中添加字段
完成！环境变量、前缀、配置匹配、状态显示都会自动处理。

注意：
- 顺序很重要 - 控制匹配优先级和回退
- 网关型 Provider（OpenRouter, AiHubMix）放在前面
- 每个条目都写出所有字段，方便复制粘贴作为模板
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderSpec:
    """
    Provider 元数据规范

    这个数据类定义了一个 LLM Provider 的所有元数据。
    使用 @dataclass(frozen=True) 使其不可变（线程安全）。

    字段说明：

    === 身份标识 ===
    name: 配置字段名（如 "dashscope"）
    keywords: 模型名关键词（用于匹配，小写）
    env_key: LiteLLM 环境变量名（如 "DASHSCOPE_API_KEY"）
    display_name: 显示名称（用于 `nanobot status`）

    === 模型前缀 ===
    litellm_prefix: LiteLLM 前缀（如 "dashscope"）
                    模型名会变成 "dashscope/{model}"
    skip_prefixes: 跳过前缀的模式（避免重复前缀）
                   如果模型名已经以这些前缀开头，不再添加前缀

    === 额外环境变量 ===
    env_extras: 额外的环境变量设置
                格式：(("ENV_NAME", "value"),)
                支持占位符：
                - {api_key}: 用户的 API 密钥
                - {api_base}: api_base 配置或 default_api_base

    === 网关/本地检测 ===
    is_gateway: 是否为网关（可以路由任意模型）
                如 OpenRouter, AiHubMix
    is_local: 是否为本地部署（vLLM, Ollama）
    detect_by_key_prefix: 通过 API 密钥前缀检测
                          如 "sk-or-" 表示 OpenRouter
    detect_by_base_keyword: 通过 API Base URL 关键词检测
                            如 "openrouter" 匹配 openrouter.ai
    default_api_base: 默认的 API Base URL

    === 网关行为 ===
    strip_model_prefix: 是否剥离模型前缀
                        某些网关不理解 "anthropic/claude-3"
                        需要剥离为 "claude-3" 再重新添加前缀

    === 模型特定覆盖 ===
    model_overrides: 针对特定模型的参数覆盖
                     格式：(("model-name", {"param": value}),)
                     如 (("kimi-k2.5", {"temperature": 1.0}),)

    占位符说明：
    env_extras 中的值支持占位符：
    - {api_key}: 替换为用户的 API 密钥
    - {api_base}: 替换为 api_base 配置或 default_api_base

    示例：
    ProviderSpec(
        name="openrouter",
        keywords=("openrouter",),
        env_key="OPENROUTER_API_KEY",
        display_name="OpenRouter",
        litellm_prefix="openrouter",
        is_gateway=True,
        detect_by_key_prefix="sk-or-",
        default_api_base="https://openrouter.ai/api/v1",
    )
    """

    # === 身份标识 ===
    name: str                       # 配置字段名
    keywords: tuple[str, ...]       # 模型名关键词（小写）
    env_key: str                    # LiteLLM 环境变量名
    display_name: str = ""          # 显示名称

    # === 模型前缀 ===
    litellm_prefix: str = ""                 # LiteLLM 前缀
    skip_prefixes: tuple[str, ...] = ()      # 跳过前缀的模式

    # === 额外环境变量 ===
    env_extras: tuple[tuple[str, str], ...] = ()

    # === 网关/本地检测 ===
    is_gateway: bool = False                 # 是否为网关
    is_local: bool = False                   # 是否为本地部署
    detect_by_key_prefix: str = ""           # API 密钥前缀检测
    detect_by_base_keyword: str = ""         # API Base 关键词检测
    default_api_base: str = ""               # 默认 API Base

    # === 网关行为 ===
    strip_model_prefix: bool = False         # 是否剥离模型前缀

    # === 模型特定覆盖 ===
    model_overrides: tuple[tuple[str, dict[str, Any]], ...] = ()

    @property
    def label(self) -> str:
        """获取显示标签（display_name 或 name 的标题形式）"""
        return self.display_name or self.name.title()


# ---------------------------------------------------------------------------
# PROVIDERS - 注册表（单一数据源）
# ---------------------------------------------------------------------------
# 顺序很重要 - 控制匹配优先级
# 网关型 Provider 放在前面（因为它们可以路由任意模型）
# 每个条目都写出所有字段，方便复制粘贴作为模板
# ---------------------------------------------------------------------------

PROVIDERS: tuple[ProviderSpec, ...] = (

    # === 网关型 Provider（通过 api_key / api_base 检测，不是模型名）===
    # 网关可以路由任意模型，所以在回退时优先匹配

    # OpenRouter: 全球网关，API 密钥以 "sk-or-" 开头
    ProviderSpec(
        name="openrouter",
        keywords=("openrouter",),
        env_key="OPENROUTER_API_KEY",
        display_name="OpenRouter",
        litellm_prefix="openrouter",        # claude-3 → openrouter/claude-3
        skip_prefixes=(),
        env_extras=(),
        is_gateway=True,
        is_local=False,
        detect_by_key_prefix="sk-or-",      # 通过密钥前缀检测
        detect_by_base_keyword="openrouter",
        default_api_base="https://openrouter.ai/api/v1",
        strip_model_prefix=False,
        model_overrides=(),
    ),

    # AiHubMix: 全球网关，OpenAI 兼容接口
    # strip_model_prefix=True: 它不理解 "anthropic/claude-3"
    # 所以我们剥离为 "claude-3" 再重新添加前缀为 "openai/claude-3"
    ProviderSpec(
        name="aihubmix",
        keywords=("aihubmix",),
        env_key="OPENAI_API_KEY",           # OpenAI 兼容
        display_name="AiHubMix",
        litellm_prefix="openai",            # → openai/{model}
        skip_prefixes=(),
        env_extras=(),
        is_gateway=True,
        is_local=False,
        detect_by_key_prefix="",
        detect_by_base_keyword="aihubmix",  # 通过 URL 关键词检测
        default_api_base="https://aihubmix.com/v1",
        strip_model_prefix=True,            # anthropic/claude-3 → claude-3 → openai/claude-3
        model_overrides=(),
    ),

    # === 标准 Provider（通过模型名关键词匹配）===

    # Anthropic: LiteLLM 原生识别 "claude-*"，不需要前缀
    ProviderSpec(
        name="anthropic",
        keywords=("anthropic", "claude"),   # 匹配包含这些关键词的模型名
        env_key="ANTHROPIC_API_KEY",
        display_name="Anthropic",
        litellm_prefix="",                  # 不需要前缀
        skip_prefixes=(),
        env_extras=(),
        is_gateway=False,
        is_local=False,
        detect_by_key_prefix="",
        detect_by_base_keyword="",
        default_api_base="",
        strip_model_prefix=False,
        model_overrides=(),
    ),

    # OpenAI: LiteLLM 原生识别 "gpt-*"，不需要前缀
    ProviderSpec(
        name="openai",
        keywords=("openai", "gpt"),
        env_key="OPENAI_API_KEY",
        display_name="OpenAI",
        litellm_prefix="",                  # 不需要前缀
        skip_prefixes=(),
        env_extras=(),
        is_gateway=False,
        is_local=False,
        detect_by_key_prefix="",
        detect_by_base_keyword="",
        default_api_base="",
        strip_model_prefix=False,
        model_overrides=(),
    ),

    # DeepSeek: 需要 "deepseek/" 前缀用于 LiteLLM 路由
    ProviderSpec(
        name="deepseek",
        keywords=("deepseek",),
        env_key="DEEPSEEK_API_KEY",
        display_name="DeepSeek",
        litellm_prefix="deepseek",          # deepseek-chat → deepseek/deepseek-chat
        skip_prefixes=("deepseek/",),       # 避免重复前缀
        env_extras=(),
        is_gateway=False,
        is_local=False,
        detect_by_key_prefix="",
        detect_by_base_keyword="",
        default_api_base="",
        strip_model_prefix=False,
        model_overrides=(),
    ),

    # Gemini: 需要 "gemini/" 前缀用于 LiteLLM
    ProviderSpec(
        name="gemini",
        keywords=("gemini",),
        env_key="GEMINI_API_KEY",
        display_name="Gemini",
        litellm_prefix="gemini",            # gemini-pro → gemini/gemini-pro
        skip_prefixes=("gemini/",),         # 避免重复前缀
        env_extras=(),
        is_gateway=False,
        is_local=False,
        detect_by_key_prefix="",
        detect_by_base_keyword="",
        default_api_base="",
        strip_model_prefix=False,
        model_overrides=(),
    ),

    # Zhipu: LiteLLM 使用 "zai/" 前缀
    # 同时镜像密钥到 ZHIPUAI_API_KEY（某些 LiteLLM 路径检查这个）
    # skip_prefixes: 当通过网关路由时不添加 "zai/" 前缀
    ProviderSpec(
        name="zhipu",
        keywords=("zhipu", "glm", "zai"),
        env_key="ZAI_API_KEY",
        display_name="Zhipu AI",
        litellm_prefix="zai",              # glm-4 → zai/glm-4
        skip_prefixes=("zhipu/", "zai/", "openrouter/", "hosted_vllm/"),
        env_extras=(
            ("ZHIPUAI_API_KEY", "{api_key}"),  # 镜像密钥
        ),
        is_gateway=False,
        is_local=False,
        detect_by_key_prefix="",
        detect_by_base_keyword="",
        default_api_base="",
        strip_model_prefix=False,
        model_overrides=(),
    ),

    # ... 更多 Provider 可以按照相同格式添加
)


# ---------------------------------------------------------------------------
# 辅助函数（在 LiteLLMProvider 中使用）
# ---------------------------------------------------------------------------

def find_by_model(model: str) -> ProviderSpec | None:
    """
    根据模型名查找 Provider

    匹配逻辑：
    1. 将模型名转换为小写
    2. 检查是否包含 Provider 的任一关键词
    3. 返回第一个匹配的 Provider

    参数:
        model: 模型名（如 "claude-opus-4-5", "gpt-4"）

    返回:
        ProviderSpec | None: 匹配的 Provider 或 None
    """
    model_lower = model.lower()
    for spec in PROVIDERS:
        if any(kw in model_lower for kw in spec.keywords):
            return spec
    return None


def find_gateway(
    provider_name: str | None,
    api_key: str | None,
    api_base: str | None
) -> ProviderSpec | None:
    """
    检测网关型 Provider

    检测顺序：
    1. 如果 provider_name 匹配网关，直接返回
    2. 如果 api_key 前缀匹配，返回对应网关
    3. 如果 api_base 包含关键词，返回对应网关

    参数:
        provider_name: Provider 名称（来自配置）
        api_key: API 密钥
        api_base: API Base URL

    返回:
        ProviderSpec | None: 匹配的网关或 None
    """
    # 1. 通过 provider_name 匹配
    if provider_name:
        for spec in PROVIDERS:
            if spec.is_gateway and spec.name == provider_name:
                return spec

    # 2. 通过 api_key 前缀匹配
    if api_key:
        for spec in PROVIDERS:
            if spec.is_gateway and spec.detect_by_key_prefix:
                if api_key.startswith(spec.detect_by_key_prefix):
                    return spec

    # 3. 通过 api_base 关键词匹配
    if api_base:
        base_lower = api_base.lower()
        for spec in PROVIDERS:
            if spec.is_gateway and spec.detect_by_base_keyword:
                if spec.detect_by_base_keyword in base_lower:
                    return spec

    return None
