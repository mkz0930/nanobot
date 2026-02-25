"""
工具基类定义 (阶段 3 核心文件)

这个模块定义了所有 Agent 工具的抽象基类 Tool。
所有工具（如文件操作、Shell 执行、Web 搜索等）都必须继承这个基类。

核心设计理念：
1. 统一接口：所有工具使用相同的接口（name, description, parameters, execute）
2. JSON Schema：使用 JSON Schema 定义参数，LLM 可以理解
3. 参数验证：自动验证工具调用的参数是否符合 Schema
4. 字符串返回：工具返回字符串结果，便于 LLM 理解和继续对话
"""

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """
    Agent 工具的抽象基类

    所有工具都必须继承这个类并实现四个核心属性/方法：
    1. name: 工具名称（LLM 调用时使用）
    2. description: 工具描述（告诉 LLM 这个工具的作用）
    3. parameters: 参数定义（JSON Schema 格式）
    4. execute: 执行逻辑（实际功能实现）

    为什么返回字符串？
    - LLM 更容易理解自然语言描述
    - 字符串结果可以直接作为上下文继续对话
    - 避免复杂的数据结构序列化问题

    示例：
        class HelloTool(Tool):
            @property
            def name(self) -> str:
                return "hello"

            @property
            def description(self) -> str:
                return "Say hello to someone"

            @property
            def parameters(self) -> dict[str, Any]:
                return {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Person's name"}
                    },
                    "required": ["name"]
                }

            async def execute(self, **kwargs: Any) -> str:
                name = kwargs.get("name", "World")
                return f"Hello, {name}!"
    """

    # JSON Schema 类型到 Python 类型的映射
    # 用于参数验证时的类型检查
    _TYPE_MAP = {
        "string": str,  # 字符串类型
        "integer": int,  # 整数类型
        "number": (int, float),  # 数字类型（整数或浮点数）
        "boolean": bool,  # 布尔类型
        "array": list,  # 数组类型
        "object": dict,  # 对象类型
    }

    @property
    @abstractmethod
    def name(self) -> str:
        """
        工具名称

        这是 LLM 调用工具时使用的标识符。
        命名规范：
        - 使用小写字母和下划线
        - 简洁明了，见名知意
        - 例如：read_file, exec, web_search

        返回:
            str: 工具的唯一名称
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        工具描述

        这是告诉 LLM 这个工具做什么的说明。
        描述应该：
        - 清晰说明工具的功能
        - 说明适用场景
        - 提示重要的使用注意事项

        例如：
        "Read the contents of a file. Use this when you need to view file contents."

        返回:
            str: 工具功能的详细描述
        """
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """
        参数定义（JSON Schema 格式）

        定义工具接受的参数及其类型、约束等。
        JSON Schema 是一个标准格式，LLM 可以理解。

        基本结构：
        {
            "type": "object",
            "properties": {
                "param_name": {
                    "type": "string",  # 参数类型
                    "description": "参数说明",  # 参数描述
                    "enum": ["option1", "option2"]  # 可选值（可选）
                }
            },
            "required": ["param_name"]  # 必需参数列表
        }

        支持的类型：
        - string: 字符串
        - integer: 整数
        - number: 数字（整数或浮点数）
        - boolean: 布尔值
        - array: 数组
        - object: 对象

        返回:
            dict: JSON Schema 格式的参数定义
        """
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """
        执行工具逻辑

        这是工具的实际功能实现。
        当 LLM 调用工具时，Agent Loop 会调用这个方法。

        参数说明：
            **kwargs: 工具参数（键值对形式）
                     参数名和类型由 parameters 属性定义

        返回:
            str: 工具执行结果（字符串格式）
                 - 成功：返回结果描述
                 - 失败：返回错误信息

        注意事项：
        - 方法是 async 的，支持异步操作
        - 必须返回字符串，不能返回其他类型
        - 应该处理异常并返回友好的错误信息
        - 结果应该简洁明了，便于 LLM 理解

        示例：
            async def execute(self, **kwargs: Any) -> str:
                try:
                    path = kwargs["path"]
                    content = Path(path).read_text()
                    return f"File content:\\n{content}"
                except Exception as e:
                    return f"Error reading file: {e}"
        """
        pass

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """
        验证工具参数是否符合 JSON Schema

        在执行工具之前，Agent Loop 会调用这个方法验证参数。
        这可以防止无效参数导致的错误。

        参数:
            params: 要验证的参数字典

        返回:
            list[str]: 错误列表
                      - 空列表表示验证通过
                      - 非空列表包含所有验证错误信息

        验证内容：
        - 类型检查：参数类型是否正确
        - 必需参数：是否缺少必需参数
        - 值约束：是否满足 enum、minimum、maximum 等约束
        - 字符串长度：是否满足 minLength、maxLength 约束
        - 嵌套验证：递归验证 object 和 array 类型

        示例：
            errors = tool.validate_params({"path": "/tmp/file.txt"})
            if errors:
                print(f"Validation failed: {errors}")
            else:
                result = await tool.execute(path="/tmp/file.txt")
        """
        schema = self.parameters or {}

        # 确保 Schema 是 object 类型
        if schema.get("type", "object") != "object":
            raise ValueError(f"Schema must be object type, got {schema.get('type')!r}")

        # 调用内部验证方法
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, val: Any, schema: dict[str, Any], path: str) -> list[str]:
        """
        内部递归验证方法

        这个方法递归验证参数值是否符合 Schema。
        支持嵌套的 object 和 array 类型。

        参数:
            val: 要验证的值
            schema: JSON Schema 定义
            path: 当前路径（用于错误信息）

        返回:
            list[str]: 错误列表
        """
        t = schema.get("type")  # 获取类型
        label = path or "parameter"  # 错误信息中的标签
        errors = []

        # 1. 类型检查
        if t in self._TYPE_MAP and not isinstance(val, self._TYPE_MAP[t]):
            return [f"{label} should be {t}"]

        # 2. 枚举值检查
        if "enum" in schema and val not in schema["enum"]:
            errors.append(f"{label} must be one of {schema['enum']}")

        # 3. 数字范围检查
        if t in ("integer", "number"):
            if "minimum" in schema and val < schema["minimum"]:
                errors.append(f"{label} must be >= {schema['minimum']}")
            if "maximum" in schema and val > schema["maximum"]:
                errors.append(f"{label} must be <= {schema['maximum']}")

        # 4. 字符串长度检查
        if t == "string":
            if "minLength" in schema and len(val) < schema["minLength"]:
                errors.append(f"{label} must be at least {schema['minLength']} chars")
            if "maxLength" in schema and len(val) > schema["maxLength"]:
                errors.append(f"{label} must be at most {schema['maxLength']} chars")

        # 5. 对象属性检查
        if t == "object":
            props = schema.get("properties", {})

            # 检查必需属性
            for k in schema.get("required", []):
                if k not in val:
                    errors.append(f"missing required {path + '.' + k if path else k}")

            # 递归验证每个属性
            for k, v in val.items():
                if k in props:
                    errors.extend(
                        self._validate(v, props[k], path + '.' + k if path else k)
                    )

        # 6. 数组元素检查
        if t == "array" and "items" in schema:
            for i, item in enumerate(val):
                errors.extend(
                    self._validate(
                        item, schema["items"], f"{path}[{i}]" if path else f"[{i}]"
                    )
                )

        return errors

    def to_schema(self) -> dict[str, Any]:
        """
        转换为 OpenAI Function Calling 格式

        LLM API（如 OpenAI、Anthropic）使用特定格式定义工具。
        这个方法将工具转换为 OpenAI 的 Function Calling 格式。

        返回格式：
        {
            "type": "function",
            "function": {
                "name": "tool_name",
                "description": "Tool description",
                "parameters": {...}  # JSON Schema
            }
        }

        返回:
            dict: OpenAI Function Calling 格式的工具定义
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
