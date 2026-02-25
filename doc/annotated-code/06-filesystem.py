"""
文件系统工具 - 文件读写编辑操作

这个模块提供了文件系统操作的工具：
1. ReadFileTool - 读取文件内容
2. WriteFileTool - 写入文件
3. EditFileTool - 编辑文件（查找替换）
4. ListDirTool - 列出目录内容

安全特性：
- 支持沙箱模式（restrict_to_workspace）
- 路径解析和验证
- 错误处理

设计思路：
- 简单直接的文件操作
- 返回清晰的错误信息
- 支持路径限制（安全）
"""

from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool


def _resolve_path(path: str, allowed_dir: Path | None = None) -> Path:
    """
    解析路径并可选地强制目录限制

    这个辅助函数用于：
    1. 解析相对路径为绝对路径
    2. 展开用户目录（~）
    3. 检查路径是否在允许的目录内（沙箱模式）

    参数:
        path: 要解析的路径
        allowed_dir: 允许的目录（如果设置，路径必须在此目录内）

    返回:
        Path: 解析后的绝对路径

    抛出:
        PermissionError: 如果路径在允许目录之外

    示例:
        # 无限制
        p = _resolve_path("~/test.txt")  # -> /home/user/test.txt

        # 有限制
        p = _resolve_path("test.txt", Path("/workspace"))  # -> /workspace/test.txt
        p = _resolve_path("/etc/passwd", Path("/workspace"))  # -> PermissionError
    """
    # 解析路径：展开 ~ 并转换为绝对路径
    resolved = Path(path).expanduser().resolve()

    # 如果设置了允许目录，检查路径是否在其中
    if allowed_dir and not str(resolved).startswith(str(allowed_dir.resolve())):
        raise PermissionError(f"Path {path} is outside allowed directory {allowed_dir}")

    return resolved


class ReadFileTool(Tool):
    """
    读取文件工具

    功能：读取指定路径的文件内容

    使用场景：
    - Agent 需要查看文件内容
    - 读取配置文件
    - 读取技能文档（SKILL.md）

    安全特性：
    - 支持路径限制（沙箱模式）
    - 检查文件是否存在
    - 检查是否为文件（不是目录）
    """

    def __init__(self, allowed_dir: Path | None = None):
        """
        初始化读取文件工具

        参数:
            allowed_dir: 允许的目录（如果设置，只能读取此目录内的文件）
        """
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file at the given path."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to read"
                }
            },
            "required": ["path"]
        }

    async def execute(self, path: str, **kwargs: Any) -> str:
        """
        执行文件读取

        参数:
            path: 文件路径

        返回:
            str: 文件内容或错误信息
        """
        try:
            # 解析路径并检查权限
            file_path = _resolve_path(path, self._allowed_dir)

            # 检查文件是否存在
            if not file_path.exists():
                return f"Error: File not found: {path}"

            # 检查是否为文件（不是目录）
            if not file_path.is_file():
                return f"Error: Not a file: {path}"

            # 读取文件内容（UTF-8 编码）
            content = file_path.read_text(encoding="utf-8")
            return content

        except PermissionError as e:
            # 路径在允许目录之外
            return f"Error: {e}"
        except Exception as e:
            # 其他错误（如编码错误）
            return f"Error reading file: {str(e)}"


class WriteFileTool(Tool):
    """
    写入文件工具

    功能：将内容写入指定路径的文件

    特性：
    - 自动创建父目录
    - 覆盖已存在的文件
    - 支持路径限制

    使用场景：
    - 创建新文件
    - 更新配置文件
    - 保存生成的代码
    """

    def __init__(self, allowed_dir: Path | None = None):
        """
        初始化写入文件工具

        参数:
            allowed_dir: 允许的目录（如果设置，只能写入此目录内的文件）
        """
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file at the given path. Creates parent directories if needed."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to write to"
                },
                "content": {
                    "type": "string",
                    "description": "The content to write"
                }
            },
            "required": ["path", "content"]
        }

    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        """
        执行文件写入

        参数:
            path: 文件路径
            content: 要写入的内容

        返回:
            str: 成功消息或错误信息
        """
        try:
            # 解析路径并检查权限
            file_path = _resolve_path(path, self._allowed_dir)

            # 创建父目录（如果不存在）
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入文件（UTF-8 编码）
            file_path.write_text(content, encoding="utf-8")

            return f"Successfully wrote {len(content)} bytes to {path}"

        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error writing file: {str(e)}"


class EditFileTool(Tool):
    """
    编辑文件工具

    功能：通过查找替换来编辑文件

    工作原理：
    1. 读取文件内容
    2. 查找 old_text
    3. 替换为 new_text
    4. 写回文件

    注意事项：
    - old_text 必须完全匹配（包括空格、换行）
    - 如果有多个匹配，会替换所有
    - 如果找不到 old_text，返回错误

    使用场景：
    - 修改配置文件
    - 更新代码
    - 批量替换
    """

    def __init__(self, allowed_dir: Path | None = None):
        """
        初始化编辑文件工具

        参数:
            allowed_dir: 允许的目录（如果设置，只能编辑此目录内的文件）
        """
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return "Edit a file by replacing old_text with new_text. The old_text must exist exactly in the file."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to edit"
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find and replace"
                },
                "new_text": {
                    "type": "string",
                    "description": "The text to replace with"
                }
            },
            "required": ["path", "old_text", "new_text"]
        }

    async def execute(self, path: str, old_text: str, new_text: str, **kwargs: Any) -> str:
        """
        执行文件编辑

        参数:
            path: 文件路径
            old_text: 要查找的文本（必须完全匹配）
            new_text: 替换后的文本

        返回:
            str: 成功消息或错误信息
        """
        try:
            # 解析路径并检查权限
            file_path = _resolve_path(path, self._allowed_dir)

            # 检查文件是否存在
            if not file_path.exists():
                return f"Error: File not found: {path}"

            # 读取文件内容
            content = file_path.read_text(encoding="utf-8")

            # 检查 old_text 是否存在
            if old_text not in content:
                return f"Error: old_text not found in file. Make sure it matches exactly."

            # 统计匹配次数
            count = content.count(old_text)

            # 替换所有匹配
            new_content = content.replace(old_text, new_text)

            # 写回文件
            file_path.write_text(new_content, encoding="utf-8")

            return f"Successfully replaced {count} occurrence(s) in {path}"

        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error editing file: {str(e)}"


class ListDirTool(Tool):
    """
    列出目录工具

    功能：列出指定目录的内容

    返回信息：
    - 文件和目录列表
    - 每个条目的类型（文件/目录）
    - 文件大小

    使用场景：
    - 浏览目录结构
    - 查找文件
    - 了解项目结构
    """

    def __init__(self, allowed_dir: Path | None = None):
        """
        初始化列出目录工具

        参数:
            allowed_dir: 允许的目录（如果设置，只能列出此目录内的内容）
        """
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return "List the contents of a directory."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to list"
                }
            },
            "required": ["path"]
        }

    async def execute(self, path: str, **kwargs: Any) -> str:
        """
        执行目录列出

        参数:
            path: 目录路径

        返回:
            str: 目录内容列表或错误信息
        """
        try:
            # 解析路径并检查权限
            dir_path = _resolve_path(path, self._allowed_dir)

            # 检查目录是否存在
            if not dir_path.exists():
                return f"Error: Directory not found: {path}"

            # 检查是否为目录
            if not dir_path.is_dir():
                return f"Error: Not a directory: {path}"

            # 列出目录内容
            entries = []
            for item in sorted(dir_path.iterdir()):
                if item.is_dir():
                    entries.append(f"[DIR]  {item.name}/")
                else:
                    size = item.stat().st_size
                    entries.append(f"[FILE] {item.name} ({size} bytes)")

            if not entries:
                return f"Directory is empty: {path}"

            return "\n".join(entries)

        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error listing directory: {str(e)}"
