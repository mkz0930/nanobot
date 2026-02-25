"""
工具基类 - 所有工具的抽象基类

这个模块定义了 nanobot 工具系统的核心抽象类。
所有工具都必须继承 Tool 类并实现其抽象方法。

设计思路：
1. 统一接口 - 所有工具遵循相同的接口规范
2. JSON Schema - 使用标准的 JSON Schema 定义参数
3. 参数验证 - 自动验证工具参数的类型和约束
4. 字符串返回 - 工具返回字符串结果（LLM 更容易理解）

为什么返回字符串？
- LLM 更容易理解自然语言描述
- 字符串结果可以直接作为上下文继续对话
- 避免复杂的数据结构序列化问题
"""

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """
    工具抽象基类

    所有工具必须实现的接口：
    1. name - 工具名称（如 "read_file"）
    2. description - 工具描述（告诉 LLM 这个工具的作用）
    3. parameters - 参数定义（JSON Schema 格式）
    4. execute - 执行工具逻辑

    使用示例：
    ```python
    class MyTool(Tool):
        @property
        def name(self) -> str:
            return "my_tool"

        @property
        def description(self) -> str:
            return "这个工具做什么"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {
                    "arg1": {"type": "string", "description": "参数1"}
                },
                "required": ["arg1"]
            }

        async def execute(self, arg1: str, **kwargs: Any) -> str:
            return f"执行结果: {arg1}"
    ```
    """

    # JSON Schema 类型到 Python 类型的映射
    # 用于参数验证
    _TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": (int, float),  # number 可以是 int 或 float
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    @property
    @abstractmethod
    def name(self) -> str:
        """
        工具名称

        这是 LLM 调用工具时使用的名称。
        命名规范：
        - 使用小写字母和下划线
        - 简洁明了（如 read_file, exec, web_search）
        - 避免使用特殊字符

        返回:
            str: 工具名称
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        工具描述

        这是告诉 LLM 这个工具做什么的说明。
        描述应该：
        - 清晰简洁
        - 说明工具的功能和用途
        - 提示使用场景和注意事项

        返回:
            str: 工具描述
        """
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """
        参数定义（JSON Schema 格式）

        使用 JSON Schema 定义工具的参数。
        JSON Schema 是一个标准格式，用于描述 JSON 数据的结构。

        基本结构：
        {
            "type": "object",
            "properties": {
                "参数名": {
                    "type": "类型",
                    "description": "参数说明"
                }
            },
            "required": ["必需参数列表"]
        }

        支持的类型：
        - string: 字符串
        - integer: 整数
        - number: 数字（整数或浮点数）
        - boolean: 布尔值
        - array: 数组
        - object: 对象

        支持的约束：
        - enum: 枚举值（如 ["utf-8", "gbk"]）
        - minimum/maximum: 数字范围
        - minLength/maxLength: 字符串长度
        - required: 必需参数

        示例：
        {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径"
                },
                "encoding": {
                    "type": "string",
                    "enum": ["utf-8", "gbk"],
                    "description": "文件编码"
                }
            },
            "required": ["path"]
        }

        返回:
            dict[str, Any]: JSON Schema 格式的参数定义
        """
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """
        执行工具逻辑

        这是工具的核心方法，实现工具的具体功能。

        参数:
            **kwargs: 工具参数（根据 parameters 定义）

        返回:
            str: 工具执行结果（字符串格式）

        注意事项：
        1. 返回值必须是字符串
        2. 如果出错，返回错误信息（不要抛出异常）
        3. 结果应该清晰易懂（LLM 会读取这个结果）
        4. 避免返回过长的内容（可以截断）

        示例：
        ```python
        async def execute(self, path: str, **kwargs: Any) -> str:
            try:
                content = Path(path).read_text()
                return content
            except Exception as e:
                return f"Error: {e}"
        ```
        """
        pass

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """
        验证工具参数

        根据 JSON Schema 验证参数是否符合要求。
        这个方法会自动检查：
        - 参数类型是否正确
        - 必需参数是否存在
        - 值是否符合约束（enum, minimum, maximum 等）

        参数:
            params: 要验证的参数字典

        返回:
            list[str]: 错误列表（如果为空，表示验证通过）

        使用示例：
        ```python
        tool = ReadFileTool()
        errors = tool.validate_params({"path": "/tmp/test.txt"})
        if errors:
            print("参数错误:", errors)
        ```
        """
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            raise ValueError(f"Schema must be object type, got {schema.get('type')!r}")
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, val: Any, schema: dict[str, Any], path: str) -> list[str]:
        """
        递归验证参数

        这是一个内部方法，递归验证参数的类型和约束。

        验证逻辑：
        1. 类型检查 - 检查值的类型是否匹配
        2. 枚举检查 - 如果有 enum，检查值是否在枚举中
        3. 范围检查 - 对于数字，检查 minimum 和 maximum
        4. 长度检查 - 对于字符串，检查 minLength 和 maxLength
        5. 必需参数检查 - 对于对象，检查 required 字段
        6. 递归验证 - 对于对象和数组，递归验证子元素

        参数:
            val: 要验证的值
            schema: JSON Schema
            path: 当前路径（用于错误消息）

        返回:
            list[str]: 错误列表
        """
        t, label = schema.get("type"), path or "parameter"

        # 1. 类型检查
        if t in self._TYPE_MAP and not isinstance(val, self._TYPE_MAP[t]):
            return [f"{label} should be {t}"]

        errors = []

        # 2. 枚举检查
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

        # 5. 对象验证（递归）
        if t == "object":
            props = schema.get("properties", {})
            # 检查必需参数
            for k in schema.get("required", []):
                if k not in val:
                    errors.append(f"missing required {path + '.' + k if path else k}")
            # 递归验证每个属性
            for k, v in val.items():
                if k in props:
                    errors.extend(self._validate(v, props[k], path + '.' + k if path else k))

        # 6. 数组验证（递归）
        if t == "array" and "items" in schema:
            for i, item in enumerate(val):
                errors.extend(self._validate(item, schema["items"], f"{path}[{i}]" if path else f"[{i}]"))

        return errors

    def to_schema(self) -> dict[str, Any]:
        """
        转换为 OpenAI Function Calling 格式

        将工具定义转换为 OpenAI Function Calling API 的格式。
        这个格式也被其他 LLM 提供商（Anthropic, Google 等）支持。

        返回格式：
        {
            "type": "function",
            "function": {
                "name": "工具名称",
                "description": "工具描述",
                "parameters": {...}  # JSON Schema
            }
        }

        返回:
            dict[str, Any]: OpenAI Function Calling 格式的工具定义
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
