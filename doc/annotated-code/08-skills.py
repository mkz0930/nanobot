"""
技能加载器 - 动态加载 Agent 技能

这个模块负责管理和加载 Agent 的技能。
技能是 Markdown 格式的文档，为 Agent 提供专业知识和能力。

核心概念：
1. 技能文档 - 每个技能是一个目录，包含 SKILL.md 文件
2. 渐进式加载 - 只加载摘要，Agent 按需读取完整内容
3. 依赖检查 - 检查技能所需的命令行工具和环境变量
4. 优先级 - 工作区技能优先于内置技能

技能结构：
workspace/
  skills/
    github/
      SKILL.md  # 技能文档
    docker/
      SKILL.md

技能文档格式：
---
name: github
description: "使用 gh CLI 与 GitHub 交互"
metadata:
  nanobot:
    emoji: "🐙"
    always: false  # 是否始终加载
    requires:
      bins: ["gh"]  # 需要的命令行工具
      env: ["GITHUB_TOKEN"]  # 需要的环境变量
---

# GitHub Skill
使用 `gh` CLI 与 GitHub 交互...
"""

import json
import os
import re
import shutil
from pathlib import Path

# 内置技能目录（相对于此文件）
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"


class SkillsLoader:
    """
    技能加载器

    职责：
    1. 发现技能 - 扫描工作区和内置技能目录
    2. 加载技能 - 读取技能文档内容
    3. 检查依赖 - 验证技能所需的工具和环境变量
    4. 构建摘要 - 生成技能列表（用于渐进式加载）

    渐进式加载策略：
    - Always-loaded skills: 完整内容加载到上下文
    - Available skills: 仅显示摘要，Agent 按需使用 read_file 加载

    为什么渐进式加载？
    - 节省 token（上下文长度有限）
    - 提高响应速度
    - 保持灵活性
    """

    def __init__(self, workspace: Path, builtin_skills_dir: Path | None = None):
        """
        初始化技能加载器

        参数:
            workspace: 工作区路径（~/.nanobot/workspace/）
            builtin_skills_dir: 内置技能目录（默认使用 nanobot/skills/）
        """
        self.workspace = workspace
        # 用户技能目录（优先级最高）
        self.workspace_skills = workspace / "skills"
        # 内置技能目录
        self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR

    def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, str]]:
        """
        列出所有可用技能

        扫描顺序：
        1. 工作区技能（~/.nanobot/workspace/skills/）
        2. 内置技能（nanobot/skills/）

        如果工作区和内置都有同名技能，工作区技能优先。

        参数:
            filter_unavailable: 是否过滤掉依赖未满足的技能

        返回:
            list[dict]: 技能信息列表
            每个字典包含：
            - name: 技能名称
            - path: SKILL.md 文件路径
            - source: 来源（workspace 或 builtin）
        """
        skills = []

        # 1. 扫描工作区技能（优先级最高）
        if self.workspace_skills.exists():
            for skill_dir in self.workspace_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        skills.append({
                            "name": skill_dir.name,
                            "path": str(skill_file),
                            "source": "workspace"
                        })

        # 2. 扫描内置技能
        if self.builtin_skills and self.builtin_skills.exists():
            for skill_dir in self.builtin_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    # 如果工作区已有同名技能，跳过
                    if skill_file.exists() and not any(s["name"] == skill_dir.name for s in skills):
                        skills.append({
                            "name": skill_dir.name,
                            "path": str(skill_file),
                            "source": "builtin"
                        })

        # 3. 过滤依赖未满足的技能
        if filter_unavailable:
            return [s for s in skills if self._check_requirements(self._get_skill_meta(s["name"]))]
        return skills

    def load_skill(self, name: str) -> str | None:
        """
        加载技能内容

        优先级：工作区 > 内置

        参数:
            name: 技能名称（目录名）

        返回:
            str | None: 技能内容（Markdown 格式）或 None（如果不存在）
        """
        # 1. 检查工作区技能
        workspace_skill = self.workspace_skills / name / "SKILL.md"
        if workspace_skill.exists():
            return workspace_skill.read_text(encoding="utf-8")

        # 2. 检查内置技能
        if self.builtin_skills:
            builtin_skill = self.builtin_skills / name / "SKILL.md"
            if builtin_skill.exists():
                return builtin_skill.read_text(encoding="utf-8")

        return None

    def load_skills_for_context(self, skill_names: list[str]) -> str:
        """
        加载指定技能的完整内容（用于上下文）

        这个方法用于加载 "always-loaded" 技能。
        这些技能的完整内容会被加载到系统提示中。

        参数:
            skill_names: 要加载的技能名称列表

        返回:
            str: 格式化的技能内容
        """
        parts = []
        for name in skill_names:
            content = self.load_skill(name)
            if content:
                # 移除 frontmatter（YAML 元数据）
                content = self._strip_frontmatter(content)
                parts.append(f"### Skill: {name}\n\n{content}")

        return "\n\n---\n\n".join(parts) if parts else ""

    def build_skills_summary(self) -> str:
        """
        构建技能摘要（用于渐进式加载）

        生成 XML 格式的技能列表，包含：
        - 技能名称
        - 技能描述
        - 文件路径
        - 可用性（依赖是否满足）
        - 缺失的依赖（如果不可用）

        Agent 可以根据这个摘要决定是否使用 read_file 加载完整内容。

        返回:
            str: XML 格式的技能摘要
        """
        all_skills = self.list_skills(filter_unavailable=False)
        if not all_skills:
            return ""

        def escape_xml(s: str) -> str:
            """转义 XML 特殊字符"""
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        lines = ["<skills>"]
        for s in all_skills:
            name = escape_xml(s["name"])
            path = s["path"]
            desc = escape_xml(self._get_skill_description(s["name"]))
            skill_meta = self._get_skill_meta(s["name"])
            available = self._check_requirements(skill_meta)

            lines.append(f"  <skill available=\"{str(available).lower()}\">")
            lines.append(f"    <name>{name}</name>")
            lines.append(f"    <description>{desc}</description>")
            lines.append(f"    <location>{path}</location>")

            # 显示缺失的依赖（如果不可用）
            if not available:
                missing = self._get_missing_requirements(skill_meta)
                if missing:
                    lines.append(f"    <requires>{escape_xml(missing)}</requires>")

            lines.append(f"  </skill>")
        lines.append("</skills>")

        return "\n".join(lines)

    def _get_missing_requirements(self, skill_meta: dict) -> str:
        """
        获取缺失的依赖描述

        检查：
        1. 命令行工具（bins）- 使用 shutil.which 检查
        2. 环境变量（env）- 使用 os.environ 检查

        参数:
            skill_meta: 技能元数据

        返回:
            str: 缺失依赖的描述（如 "CLI: gh, ENV: GITHUB_TOKEN"）
        """
        missing = []
        requires = skill_meta.get("requires", {})

        # 检查命令行工具
        for b in requires.get("bins", []):
            if not shutil.which(b):
                missing.append(f"CLI: {b}")

        # 检查环境变量
        for env in requires.get("env", []):
            if not os.environ.get(env):
                missing.append(f"ENV: {env}")

        return ", ".join(missing)

    def _get_skill_description(self, name: str) -> str:
        """
        获取技能描述

        从技能的 frontmatter 中提取 description 字段。

        参数:
            name: 技能名称

        返回:
            str: 技能描述（如果没有，返回技能名称）
        """
        meta = self.get_skill_metadata(name)
        if meta and meta.get("description"):
            return meta["description"]
        return name  # 回退到技能名称

    def _strip_frontmatter(self, content: str) -> str:
        """
        移除 Markdown 的 YAML frontmatter

        Frontmatter 格式：
        ---
        key: value
        ---

        参数:
            content: Markdown 内容

        返回:
            str: 移除 frontmatter 后的内容
        """
        if content.startswith("---"):
            match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
            if match:
                return content[match.end():].strip()
        return content

    def _parse_nanobot_metadata(self, raw: str) -> dict:
        """
        解析 nanobot 元数据

        从 frontmatter 的 metadata 字段中提取 nanobot 配置。
        metadata 字段是 JSON 格式。

        参数:
            raw: metadata 字段的值（JSON 字符串）

        返回:
            dict: nanobot 元数据
        """
        try:
            data = json.loads(raw)
            return data.get("nanobot", {}) if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _check_requirements(self, skill_meta: dict) -> bool:
        """
        检查技能依赖是否满足

        检查项：
        1. 命令行工具（bins）- 必须在 PATH 中
        2. 环境变量（env）- 必须已设置

        参数:
            skill_meta: 技能元数据

        返回:
            bool: 依赖是否满足
        """
        requires = skill_meta.get("requires", {})

        # 检查命令行工具
        for b in requires.get("bins", []):
            if not shutil.which(b):
                return False

        # 检查环境变量
        for env in requires.get("env", []):
            if not os.environ.get(env):
                return False

        return True

    def _get_skill_meta(self, name: str) -> dict:
        """
        获取技能的 nanobot 元数据

        从 frontmatter 的 metadata 字段中提取。

        参数:
            name: 技能名称

        返回:
            dict: nanobot 元数据
        """
        meta = self.get_skill_metadata(name) or {}
        return self._parse_nanobot_metadata(meta.get("metadata", ""))

    def get_always_skills(self) -> list[str]:
        """
        获取始终加载的技能

        始终加载的技能：
        - 在 frontmatter 中设置 always: true
        - 依赖已满足

        这些技能的完整内容会被加载到系统提示中。

        返回:
            list[str]: 始终加载的技能名称列表
        """
        result = []
        for s in self.list_skills(filter_unavailable=True):
            meta = self.get_skill_metadata(s["name"]) or {}
            skill_meta = self._parse_nanobot_metadata(meta.get("metadata", ""))
            # 检查 always 标记（支持两种格式）
            if skill_meta.get("always") or meta.get("always"):
                result.append(s["name"])
        return result

    def get_skill_metadata(self, name: str) -> dict | None:
        """
        获取技能的 frontmatter 元数据

        解析 YAML frontmatter（简单解析，不使用 YAML 库）。

        参数:
            name: 技能名称

        返回:
            dict | None: 元数据字典或 None
        """
        content = self.load_skill(name)
        if not content:
            return None

        # 检查是否有 frontmatter
        if content.startswith("---"):
            match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if match:
                # 简单的 YAML 解析（仅支持 key: value 格式）
                metadata = {}
                for line in match.group(1).split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        metadata[key.strip()] = value.strip().strip('"\'')
                return metadata

        return None
