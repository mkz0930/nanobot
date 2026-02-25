"""
Shell 执行工具 - 执行命令行命令

这个模块提供了执行 Shell 命令的工具。
这是一个强大但需要谨慎使用的工具。

功能：
- 执行任意 Shell 命令
- 捕获标准输出和标准错误
- 超时控制
- 安全防护（危险命令检测）

安全特性：
1. 命令黑名单 - 阻止危险命令（rm -rf, format 等）
2. 命令白名单 - 只允许特定命令（可选）
3. 沙箱模式 - 限制路径访问
4. 超时限制 - 防止命令无限运行

设计思路：
- 默认拒绝危险命令
- 支持自定义安全策略
- 返回详细的执行结果
"""

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool


class ExecTool(Tool):
    """
    Shell 执行工具

    这是一个强大的工具，允许 Agent 执行 Shell 命令。
    但同时也是最危险的工具，需要谨慎配置。

    安全机制：
    1. 危险命令检测 - 使用正则表达式检测危险模式
    2. 超时限制 - 防止命令无限运行
    3. 沙箱模式 - 限制文件访问范围
    4. 工作目录限制 - 在指定目录执行命令

    使用场景：
    - 运行测试
    - 安装依赖
    - Git 操作
    - 构建项目
    """

    def __init__(
        self,
        timeout: int = 60,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
    ):
        """
        初始化 Shell 执行工具

        参数:
            timeout: 命令超时时间（秒）
            working_dir: 工作目录（命令在此目录执行）
            deny_patterns: 拒绝的命令模式（正则表达式列表）
            allow_patterns: 允许的命令模式（如果设置，只允许匹配的命令）
            restrict_to_workspace: 是否启用沙箱模式
        """
        self.timeout = timeout
        self.working_dir = working_dir
        # 默认的危险命令模式
        self.deny_patterns = deny_patterns or [
            r"\brm\s+-[rf]{1,2}\b",          # rm -r, rm -rf, rm -fr
            r"\bdel\s+/[fq]\b",              # del /f, del /q (Windows)
            r"\brmdir\s+/s\b",               # rmdir /s (Windows)
            r"\b(format|mkfs|diskpart)\b",   # 磁盘格式化
            r"\bdd\s+if=",                   # dd 命令（可能覆盖磁盘）
            r">\s*/dev/sd",                  # 写入磁盘设备
            r"\b(shutdown|reboot|poweroff)\b",  # 系统关机/重启
            r":\(\)\s*\{.*\};\s*:",          # Fork bomb（递归进程）
        ]
        self.allow_patterns = allow_patterns or []
        self.restrict_to_workspace = restrict_to_workspace

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return "Execute a shell command and return its output. Use with caution."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                },
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory for the command"
                }
            },
            "required": ["command"]
        }

    async def execute(self, command: str, working_dir: str | None = None, **kwargs: Any) -> str:
        """
        执行 Shell 命令

        流程：
        1. 确定工作目录
        2. 安全检查（危险命令检测）
        3. 创建子进程执行命令
        4. 等待命令完成（带超时）
        5. 收集输出和错误
        6. 返回结果

        参数:
            command: 要执行的命令
            working_dir: 工作目录（可选，覆盖默认工作目录）

        返回:
            str: 命令输出或错误信息
        """
        # 1. 确定工作目录
        cwd = working_dir or self.working_dir or os.getcwd()

        # 2. 安全检查
        guard_error = self._guard_command(command, cwd)
        if guard_error:
            return guard_error

        try:
            # 3. 创建子进程
            # asyncio.create_subprocess_shell 创建一个异步子进程
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,  # 捕获标准输出
                stderr=asyncio.subprocess.PIPE,  # 捕获标准错误
                cwd=cwd,  # 设置工作目录
            )

            # 4. 等待命令完成（带超时）
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),  # 等待进程结束并获取输出
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                # 超时，杀死进程
                process.kill()
                return f"Error: Command timed out after {self.timeout} seconds"

            # 5. 收集输出
            output_parts = []

            # 标准输出
            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))

            # 标准错误
            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text}")

            # 退出码（如果非零）
            if process.returncode != 0:
                output_parts.append(f"\nExit code: {process.returncode}")

            result = "\n".join(output_parts) if output_parts else "(no output)"

            # 6. 截断过长的输出
            max_len = 10000
            if len(result) > max_len:
                result = result[:max_len] + f"\n... (truncated, {len(result) - max_len} more chars)"

            return result

        except Exception as e:
            return f"Error executing command: {str(e)}"

    def _guard_command(self, command: str, cwd: str) -> str | None:
        """
        安全防护 - 检测危险命令

        这是一个"尽力而为"的安全检查，不能保证 100% 安全。
        主要目的是防止常见的误操作和明显的危险命令。

        检查项：
        1. 危险命令模式（deny_patterns）
        2. 命令白名单（allow_patterns，如果设置）
        3. 路径遍历（.. 检测）
        4. 工作目录外的路径访问（沙箱模式）

        参数:
            command: 要检查的命令
            cwd: 工作目录

        返回:
            str | None: 如果命令被阻止，返回错误信息；否则返回 None
        """
        cmd = command.strip()
        lower = cmd.lower()

        # 1. 检查危险命令模式
        for pattern in self.deny_patterns:
            if re.search(pattern, lower):
                return "Error: Command blocked by safety guard (dangerous pattern detected)"

        # 2. 检查命令白名单
        if self.allow_patterns:
            if not any(re.search(p, lower) for p in self.allow_patterns):
                return "Error: Command blocked by safety guard (not in allowlist)"

        # 3. 沙箱模式检查
        if self.restrict_to_workspace:
            # 检查路径遍历
            if "..\\" in cmd or "../" in cmd:
                return "Error: Command blocked by safety guard (path traversal detected)"

            cwd_path = Path(cwd).resolve()

            # 提取命令中的路径
            # Windows 路径：C:\path\to\file
            win_paths = re.findall(r"[A-Za-z]:\\[^\\\"']+", cmd)
            # POSIX 绝对路径：/path/to/file
            # 只匹配绝对路径，避免误报相对路径（如 .venv/bin/python）
            posix_paths = re.findall(r"(?:^|[\s|>])(/[^\s\"'>]+)", cmd)

            # 检查每个路径是否在工作目录内
            for raw in win_paths + posix_paths:
                try:
                    p = Path(raw.strip()).resolve()
                except Exception:
                    continue
                # 如果是绝对路径且不在工作目录内，阻止
                if p.is_absolute() and cwd_path not in p.parents and p != cwd_path:
                    return "Error: Command blocked by safety guard (path outside working dir)"

        return None
