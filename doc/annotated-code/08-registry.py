"""
Provider 注册表 (阶段 5 核心文件)

这是 LLM Provider 元数据的单一数据源（Single Source of Truth）。
所有 Provider 的配置、环境变量、模型前缀等信息都集中在这里管理。

核心设计理念：
1. 单一数据源：所有 Provider 信息集中在 PROVIDERS 元组中
2. 声明式配置：使用 @dataclass 定义 Provider 元数据
3. 自动处理：环境变量、模型前缀、配置匹配都自动派生
4. 易于扩展：添加新 Provider 只需 2 步

添加新 Provider 的步骤：
  1. 在 PROVIDERS 中添加一个 ProviderSpec
  2. 在 config/schema.py 的 ProvidersConfig 中添加字段
  完成！环境变量、前缀、配置匹配、状态显示都会自动工作。

Provider 类型：
1. 网关型（Gateway）：可以路由任何模型（如 OpenRouter、AiHubMix）
2. 标准型（Standard）：特定厂商的 API（如 Anthropic、OpenAI）
3. 本地型（Local）：本地部署（如 vLLM、Ollama）

注意：PROVIDERS 的顺序很重要，它控制匹配优先级和回退逻辑。
      网关型 Provider 应该放在前面。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderSpec:
    """
    单个 LLM Provider 的元数据规范

    这个数据类定义了一个 Provider 的所有配置信息。
    使用 frozen=True 使其不可变，确保配置的稳定性。

    占位符说明（用于 env_extras 字段）：
      {api_key}  — 用户的 API 密钥
      {api_base} — 配置中的 api_base，或此规范的 default_api_base

    字段分类：
    1. 身份标识：name, keywords, env_key, display_name
    2. 模型前缀：litellm_prefix, skip_prefixes
    3. 环境变量：env_extras
    4. 检测逻辑：is_gateway, is_local, detect_by_*
    5. 网关行为：strip_model_prefix
    6. 模型覆盖：model_overrides
    """

    # ========== 身份标识 ==========

    name: str
    """
    配置字段名称

    这是在 config.json 中使用的字段名。
    例如：config.json 中的 "providers.openrouter.apiKey"

    示例：
        "openrouter", "anthropic", "deepseek"
    """

    keywords: tuple[str, ...]
    """
    模型名称关键词（用于匹配）

    当用户指定模型名称时，系统会检查模型名是否包含这些关键词。
    所有关键词应该是小写的。

    示例：
        ("openrouter",)  # 匹配包含 "openrouter" 的模型名
        ("anthropic", "claude")  # 匹配包含 "anthropic" 或 "claude" 的模型名
        ("zhipu", "glm", "zai")  # 匹配包含任一关键词的模型名

    匹配逻辑：
        model = "claude-opus-4-5"
        keywords = ("anthropic", "claude")
        # 匹配成功，因为 "claude" in "claude-opus-4-5"
    """

    env_key: str
    """
    LiteLLM 环境变量名

    LiteLLM 使用环境变量来获取 API 密钥。
    这个字段指定 LiteLLM 期望的环境变量名。

    示例：
        "ANTHROPIC_API_KEY"  # Anthropic
        "OPENAI_API_KEY"     # OpenAI
        "DEEPSEEK_API_KEY"   # DeepSeek

    系统会自动设置：
        os.environ[env_key] = user_api_key
    """

    display_name: str = ""
    """
    显示名称

    在 `nanobot status` 命令中显示的友好名称。
    如果为空，使用 name.title() 作为默认值。

    示例：
        "OpenRouter"  # 显示为 "OpenRouter"
        "Anthropic"   # 显示为 "Anthropic"
        "Zhipu AI"    # 显示为 "Zhipu AI"
    """

    # ========== 模型前缀 ==========

    litellm_prefix: str = ""
    """
    LiteLLM 模型前缀

    LiteLLM 使用前缀来路由模型到正确的 Provider。
    如果指定，系统会自动为模型名添加前缀。

    示例：
        litellm_prefix = "deepseek"
        用户模型：deepseek-chat
        实际调用：deepseek/deepseek-chat

        litellm_prefix = "openrouter"
        用户模型：claude-opus-4-5
        实际调用：openrouter/claude-opus-4-5

    特殊情况：
        litellm_prefix = ""  # 不添加前缀
        # Anthropic 和 OpenAI 不需要前缀，LiteLLM 原生支持
    """

    skip_prefixes: tuple[str, ...] = ()
    """
    跳过前缀的条件

    如果模型名已经以这些前缀开头，不再添加 litellm_prefix。
    用于避免重复前缀。

    示例：
        litellm_prefix = "deepseek"
        skip_prefixes = ("deepseek/",)

        用户模型：deepseek-chat
        → 添加前缀：deepseek/deepseek-chat

        用户模型：deepseek/deepseek-chat
        → 跳过前缀：deepseek/deepseek-chat（已有前缀）

    为什么需要？
        防止通过网关路由时出现 "openrouter/deepseek/deepseek-chat" 这样的双重前缀。
    """

    # ========== 额外环境变量 ==========

    env_extras: tuple[tuple[str, str], ...] = ()
    """
    额外的环境变量设置

    某些 Provider 需要设置多个环境变量。
    格式：((变量名, 值模板), ...)

    占位符：
        {api_key}  — 用户的 API 密钥
        {api_base} — API 基础 URL

    示例：
        env_extras = (
            ("ZHIPUAI_API_KEY", "{api_key}"),
        )
        # 设置 ZHIPUAI_API_KEY = 用户的 API 密钥

        env_extras = (
            ("CUSTOM_API_KEY", "{api_key}"),
            ("CUSTOM_API_BASE", "{api_base}"),
        )
        # 设置两个环境变量

    为什么需要？
        某些 LiteLLM 路径检查不同的环境变量名。
        例如：Zhipu 的某些路径检查 ZHIPUAI_API_KEY 而不是 ZAI_API_KEY。
    """

    # ========== 网关/本地检测 ==========

    is_gateway: bool = False
    """
    是否为网关型 Provider

    网关型 Provider 可以路由任何模型，不限于特定厂商。

    示例：
        OpenRouter: is_gateway=True  # 可以路由 Anthropic、OpenAI 等任何模型
        AiHubMix: is_gateway=True    # 可以路由多个厂商的模型
        Anthropic: is_gateway=False  # 只能使用 Anthropic 的模型

    影响：
        - 网关型 Provider 在回退逻辑中优先级更高
        - 网关型 Provider 通过 API 密钥或 API 基础 URL 检测，而不是模型名
    """

    is_local: bool = False
    """
    是否为本地部署

    本地部署的 Provider（如 vLLM、Ollama）不需要 API 密钥。

    示例：
        vLLM: is_local=True
        Ollama: is_local=True
        Anthropic: is_local=False

    影响：
        - 本地 Provider 不检查 API 密钥
        - 状态显示时标记为 "local"
    """

    detect_by_key_prefix: str = ""
    """
    通过 API 密钥前缀检测

    某些 Provider 的 API 密钥有特定前缀。
    如果用户的 API 密钥以此前缀开头，自动识别为该 Provider。

    示例：
        detect_by_key_prefix = "sk-or-"
        用户密钥：sk-or-v1-abc123...
        → 自动识别为 OpenRouter

    为什么需要？
        网关型 Provider 需要通过密钥前缀识别，因为模型名可能是任意的。
    """

    detect_by_base_keyword: str = ""
    """
    通过 API 基础 URL 关键词检测

    如果用户配置的 api_base 包含此关键词，识别为该 Provider。

    示例：
        detect_by_base_keyword = "openrouter"
        用户配置：api_base = "https://openrouter.ai/api/v1"
        → 自动识别为 OpenRouter

        detect_by_base_keyword = "aihubmix"
        用户配置：api_base = "https://aihubmix.com/v1"
        → 自动识别为 AiHubMix

    为什么需要？
        网关型 Provider 可能使用自定义域名，需要通过 URL 识别。
    """

    default_api_base: str = ""
    """
    默认 API 基础 URL

    如果用户没有配置 api_base，使用此默认值。

    示例：
        default_api_base = "https://openrouter.ai/api/v1"
        # 用户不配置 api_base 时，自动使用此 URL

    为什么需要？
        某些 Provider 需要特定的 API 端点。
    """

    # ========== 网关行为 ==========

    strip_model_prefix: bool = False
    """
    是否剥离模型前缀

    某些网关不理解 "provider/model" 格式，需要剥离前缀。

    示例：
        strip_model_prefix = True
        用户模型：anthropic/claude-opus-4-5
        → 剥离前缀：claude-opus-4-5
        → 添加网关前缀：openai/claude-opus-4-5

    为什么需要？
        AiHubMix 使用 OpenAI 兼容接口，不理解 "anthropic/" 前缀。
        需要剥离后重新添加 "openai/" 前缀。

    流程：
        1. 用户指定：anthropic/claude-opus-4-5
        2. 剥离前缀：claude-opus-4-5
        3. 添加网关前缀：openai/claude-opus-4-5
        4. 发送给 AiHubMix
    """

    # ========== 模型覆盖 ==========

    model_overrides: tuple[tuple[str, dict[str, Any]], ...] = ()
    """
    针对特定模型的参数覆盖

    某些模型需要特殊的参数设置。

    格式：((模型名, 参数字典), ...)

    示例：
        model_overrides = (
            ("kimi-k2.5", {"temperature": 1.0}),
        )
        # 当使用 kimi-k2.5 模型时，强制 temperature=1.0

        model_overrides = (
            ("deepseek-r1", {"temperature": 1.0}),
            ("deepseek-r1-distill", {"temperature": 1.0}),
        )
        # 多个模型可以有不同的覆盖

    为什么需要？
        某些模型对参数有特殊要求。
        例如：Kimi K2.5 要求 temperature=1.0 才能正常工作。
    """

    @property
    def label(self) -> str:
        """
        获取显示标签

        返回 display_name，如果为空则返回 name.title()。

        示例：
            display_name = "OpenRouter" → "OpenRouter"
            display_name = "" and name = "deepseek" → "Deepseek"
        """
        return self.display_name or self.name.title()


# ===========================================================================
# PROVIDERS — Provider 注册表
# ===========================================================================
#
# 这是所有 Provider 元数据的集中定义。
# 顺序很重要：它控制匹配优先级和回退逻辑。
#
# 组织原则：
# 1. 网关型 Provider 放在前面（优先级高）
# 2. 标准型 Provider 按字母顺序排列
# 3. 本地型 Provider 放在最后
#
# 每个条目都写出所有字段，方便复制粘贴作为模板。
# ===========================================================================

PROVIDERS: tuple[ProviderSpec, ...] = (

    # =======================================================================
    # 网关型 Provider（通过 api_key / api_base 检测，不是模型名）
    # =======================================================================
    # 网关可以路由任何模型，所以在回退逻辑中优先级最高。

    # OpenRouter: 全球网关，密钥以 "sk-or-" 开头
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
        detect_by_base_keyword="openrouter", # 通过 URL 关键词检测
        default_api_base="https://openrouter.ai/api/v1",
        strip_model_prefix=False,
        model_overrides=(),
    ),

    # AiHubMix: 全球网关，OpenAI 兼容接口
    # strip_model_prefix=True: 它不理解 "anthropic/claude-3"，
    # 所以我们剥离到裸 "claude-3"，然后重新添加前缀为 "openai/claude-3"
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
        detect_by_base_keyword="aihubmix",  # 通过 URL 检测
        default_api_base="https://aihubmix.com/v1",
        strip_model_prefix=True,            # anthropic/claude-3 → claude-3 → openai/claude-3
        model_overrides=(),
    ),

    # =======================================================================
    # 标准型 Provider（通过模型名关键词匹配）
    # =======================================================================

    # Anthropic: LiteLLM 原生识别 "claude-*"，不需要前缀
    ProviderSpec(
        name="anthropic",
        keywords=("anthropic", "claude"),   # 匹配包含 "anthropic" 或 "claude" 的模型名
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
        keywords=("openai", "gpt"),         # 匹配包含 "openai" 或 "gpt" 的模型名
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
    # 同时镜像密钥到 ZHIPUAI_API_KEY（某些 LiteLLM 路径检查该变量）
    # skip_prefixes: 当已经通过网关路由时，不添加 "zai/" 前缀
    ProviderSpec(
        name="zhipu",
        keywords=("zhipu", "glm", "zai"),   # 匹配多个关键词
        env_key="ZAI_API_KEY",
        display_name="Zhipu AI",
        litellm_prefix="zai",               # glm-4 → zai/glm-4
        skip_prefixes=("zhipu/", "zai/", "openrouter/", "hosted_vllm/"),
        env_extras=(
            ("ZHIPUAI_API_KEY", "{api_key}"),  # 镜像密钥到另一个变量
        ),
        is_gateway=False,
        is_local=False,
        detect_by_key_prefix="",
        detect_by_base_keyword="",
        default_api_base="",
        strip_model_prefix=False,
        model_overrides=(),
    ),

    # ... 更多 Provider 可以按相同格式添加 ...

)


# ===========================================================================
# 使用示例
# ===========================================================================
#
# 1. 查找 Provider:
#    for spec in PROVIDERS:
#        if "claude" in model_name.lower():
#            # 找到 Anthropic Provider
#            break
#
# 2. 设置环境变量:
#    os.environ[spec.env_key] = user_api_key
#    for env_name, template in spec.env_extras:
#        value = template.format(api_key=user_api_key, api_base=api_base)
#        os.environ[env_name] = value
#
# 3. 添加模型前缀:
#    if spec.litellm_prefix and not any(model.startswith(p) for p in spec.skip_prefixes):
#        model = f"{spec.litellm_prefix}/{model}"
#
# 4. 检测网关:
#    if spec.detect_by_key_prefix and api_key.startswith(spec.detect_by_key_prefix):
#        # 使用此 Provider
#    if spec.detect_by_base_keyword and spec.detect_by_base_keyword in api_base:
#        # 使用此 Provider
#
# ===========================================================================
