# 阶段 5: Provider 系统掌握

**难度**: ⭐⭐⭐
**预计时间**: 2-3 天
**前置要求**: 完成阶段 1-4

---

## 🎯 学习目标

- ✅ 深入理解 Provider Registry 模式
- ✅ 配置和使用多个 LLM 提供商
- ✅ 添加新的 Provider
- ✅ 理解模型前缀和环境变量机制
- ✅ 实现 Provider 的自动检测

---

## 📖 Provider 系统架构

### Provider Registry 模式

**核心思想**: 所有 Provider 元数据集中管理，通过声明式配置添加新 Provider。

**优势**:
- 无需修改业务逻辑
- 自动处理环境变量
- 统一的模型前缀规则
- 易于扩展和维护

### ProviderSpec 结构

```python
@dataclass(frozen=True)
class ProviderSpec:
    # 身份标识
    name: str                       # 配置字段名
    keywords: tuple[str, ...]       # 模型名关键词
    env_key: str                    # 环境变量名
    display_name: str = ""          # 显示名称

    # 模型前缀
    litellm_prefix: str = ""        # LiteLLM 前缀
    skip_prefixes: tuple = ()       # 跳过前缀列表

    # 环境变量
    env_extras: tuple = ()          # 额外环境变量

    # 网关检测
    is_gateway: bool = False        # 是否为网关
    is_local: bool = False          # 是否为本地部署
    detect_by_key_prefix: str = ""  # API key 前缀检测
    detect_by_base_keyword: str = "" # API base 关键词检测
    default_api_base: str = ""      # 默认 API base

    # 网关行为
    strip_model_prefix: bool = False # 是否剥离模型前缀

    # 模型覆盖
    model_overrides: tuple = ()     # 特定模型的参数覆盖
```

---

## 🔧 配置多个 Provider

### 配置示例

```json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-...",
      "apiBase": "https://openrouter.ai/api/v1"
    },
    "anthropic": {
      "apiKey": "sk-ant-..."
    },
    "openai": {
      "apiKey": "sk-..."
    },
    "deepseek": {
      "apiKey": "sk-..."
    },
    "vllm": {
      "apiKey": "dummy",
      "apiBase": "http://localhost:8000/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5"
    }
  }
}
```

### 模型选择策略

```python
# 1. 直接指定 Provider
model = "openrouter/anthropic/claude-opus-4-5"

# 2. 自动匹配（通过关键词）
model = "claude-opus-4-5"  # → 匹配到 anthropic

# 3. 网关路由
model = "gpt-4"  # → 通过 OpenRouter 路由
```

---

## 🛠️ 添加新 Provider

### 步骤 1: 添加 ProviderSpec

```python
# nanobot/providers/registry.py

ProviderSpec(
    name="cohere",
    keywords=("cohere", "command"),
    env_key="COHERE_API_KEY",
    display_name="Cohere",
    litellm_prefix="cohere",
    skip_prefixes=("cohere/",),
    default_api_base="https://api.cohere.ai/v1",
)
```

### 步骤 2: 添加配置字段

```python
# nanobot/config/schema.py

class ProvidersConfig(BaseModel):
    # ... 其他 providers
    cohere: ProviderConfig = ProviderConfig()
```

### 步骤 3: 配置和测试

```json
{
  "providers": {
    "cohere": {
      "apiKey": "your-cohere-key"
    }
  },
  "agents": {
    "defaults": {
      "model": "cohere/command-r-plus"
    }
  }
}
```

---

## 📝 实践任务

### 任务 1: 配置多 Provider

配置至少 3 个不同的 Provider，测试切换。

### 任务 2: 添加 Groq Provider

添加 Groq 支持（如果尚未支持）。

### 任务 3: 本地模型部署

使用 vLLM 部署本地模型并配置。

---

## ✅ 阶段检验

- [ ] 理解 Provider Registry 模式
- [ ] 配置多个 Provider
- [ ] 添加新 Provider
- [ ] 测试模型切换

---

## 🎉 恭喜！

准备好了吗？让我们进入 [阶段 6: Channel 集成入门](./06-Channel集成入门.md)！
