"""
技能加载器 (阶段 4 核心文件)

这个模块负责加载和管理 Agent 的技能文档。
技能是 Markdown 格式的知识文档，教会 Agent 如何使用特定工具或完成特定任务。

核心设计理念：
1. 渐进式加载：仅在需要时加载完整技能内容，节省 token
2. 优先级系统：工作区技能 > 内置技能
3. 依赖检查：自动检查技能所需的命令行工具和环境变量
4. Frontmatter 元数据：使用 YAML frontmatter 存储技能配置

技能目录结构：
    skills/
    ├── github/
    │   └── SKILL.md
    ├── weather/
    │   └── SKILL.md
    └── tmux/
        └── SKILL.md
"""

import json
import os
import re
import shutil
from pathlib import Path

# 内置技能目录（相对于此文件）
# 指向 nanobot/skills/ 目录
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"


class SkillsLoader:
    """
    技能加载器

    负责扫描、加载和管理 Agent 的技能文档。
    支持两种技能来源：
    1. 工作区技能（~/.nanobot/workspace/skills/）- 用户自定义
    2. 内置技能（nanobot/skills/）- 系统提供

    技能文档格式：
        ---
        name: github
        description: "使用 gh CLI 与 GitHub 交互"
        metadata:
          nanobot:
            emoji: "🐙"
            always_load: false
            requires:
              bins: ["gh"]  # 需要的命令行工具
              env: ["GITHUB_TOKEN"]  # 需要的环境变量
        ---

        # GitHub Skill

        技能内容...

    渐进式加载策略：
    1. Always-loaded skills: 完整内容加载到上下文（always_load: true）
    2. Available skills: 仅显示摘要，Agent 按需使用 read_file 加载
    """

    def __init__(self, workspace: Path, builtin_skills_dir: Path | None = None):
        """
        初始化技能加载器

        参数:
            workspace: 工作区路径（~/.nanobot/workspace）
            builtin_skills_dir: 内置技能目录（默认为 nanobot/skills）
        """
        self.workspace = workspace
        self.workspace_skills = workspace / "skills"  # 用户技能目录
        self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR  # 内置技能目录

    def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, str]]:
        """
        列出所有可用技能

        扫描工作区和内置技能目录，返回技能列表。
        工作区技能优先级高于内置技能（可以覆盖同名内置技能）。

        参数:
            filter_unavailable: 是否过滤掉依赖未满足的技能

        返回:
            技能信息列表，每个元素包含：
            - name: 技能名称（目录名）
            - path: SKILL.md 文件路径
            - source: 来源（"workspace" 或 "builtin"）

        示例:
            [
                {"name": "github", "path": "/path/to/github/SKILL.md", "source": "builtin"},
                {"name": "docker", "path": "/path/to/docker/SKILL.md", "source": "workspace"}
            ]
        """
        skills = []

        # 1. 扫描工作区技能（最高优先级）
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
                    # 如果工作区已有同名技能，跳过内置技能
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
        加载指定技能的内容

        按优先级查找技能：工作区 > 内置

        参数:
            name: 技能名称（目录名）

        返回:
            技能的完整 Markdown 内容，如果未找到返回 None

        示例:
            content = loader.load_skill("github")
            if content:
                print(content)  # 打印 GitHub 技能的完整内容
        """
        # 优先检查工作区技能
        workspace_skill = self.workspace_skills / name / "SKILL.md"
        if workspace_skill.exists():
            return workspace_skill.read_text(encoding="utf-8")

        # 检查内置技能
        if self.builtin_skills:
            builtin_skill = self.builtin_skills / name / "SKILL.md"
            if builtin_skill.exists():
                return builtin_skill.read_text(encoding="utf-8")

        return None

    def load_skills_for_context(self, skill_names: list[str]) -> str:
        """
        加载指定技能用于上下文

        用于 always-loaded skills，将完整内容加载到 Agent 上下文中。
        会自动去除 frontmatter，只保留实际内容。

        参数:
            skill_names: 要加载的技能名称列表

        返回:
            格式化的技能内容（多个技能用分隔符连接）

        示例:
            # 加载 github 和 weather 技能
            content = loader.load_skills_for_context(["github", "weather"])
            # 返回格式：
            # ### Skill: github
            #
            # GitHub 技能内容...
            #
            # ---
            #
            # ### Skill: weather
            #
            # Weather 技能内容...
        """
        parts = []
        for name in skill_names:
            content = self.load_skill(name)
            if content:
                # 去除 frontmatter（--- ... --- 部分）
                content = self._strip_frontmatter(content)
                parts.append(f"### Skill: {name}\n\n{content}")

        return "\n\n---\n\n".join(parts) if parts else ""

    def build_skills_summary(self) -> str:
        """
        构建技能摘要（用于渐进式加载）

        生成所有技能的摘要信息（名称、描述、路径、可用性）。
        Agent 可以根据摘要决定是否使用 read_file 加载完整内容。

        返回:
            XML 格式的技能摘要

        示例输出:
            <skills>
              <skill available="true">
                <name>github</name>
                <description>使用 gh CLI 与 GitHub 交互</description>
                <location>/path/to/github/SKILL.md</location>
              </skill>
              <skill available="false">
                <name>docker</name>
                <description>Docker 容器管理</description>
                <location>/path/to/docker/SKILL.md</location>
                <requires>CLI: docker</requires>
              </skill>
            </skills>

        为什么使用 XML 格式？
        - 结构化：便于 LLM 解析
        - 紧凑：比 JSON 更节省 token
        - 可读：人类也容易阅读
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

            # 如果技能不可用，显示缺失的依赖
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

        检查技能所需的命令行工具和环境变量，返回缺失项。

        参数:
            skill_meta: 技能元数据（从 frontmatter 解析）

        返回:
            缺失依赖的描述字符串

        示例:
            "CLI: docker, ENV: DOCKER_HOST"
        """
        missing = []
        requires = skill_meta.get("requires", {})

        # 检查命令行工具
        for b in requires.get("bins", []):
            if not shutil.which(b):  # shutil.which() 检查命令是否在 PATH 中
                missing.append(f"CLI: {b}")

        # 检查环境变量
        for env in requires.get("env", []):
            if not os.environ.get(env):
                missing.append(f"ENV: {env}")

        return ", ".join(missing)

    def _get_skill_description(self, name: str) -> str:
        """
        获取技能描述

        从 frontmatter 中提取 description 字段。

        参数:
            name: 技能名称

        返回:
            技能描述，如果未找到返回技能名称
        """
        meta = self.get_skill_metadata(name)
        if meta and meta.get("description"):
            return meta["description"]
        return name  # 回退到技能名称

    def _strip_frontmatter(self, content: str) -> str:
        """
        去除 Markdown 的 YAML frontmatter

        Frontmatter 格式：
            ---
            key: value
            ---

        参数:
            content: 完整的 Markdown 内容

        返回:
            去除 frontmatter 后的内容
        """
        if content.startswith("---"):
            # 使用正则表达式匹配 frontmatter
            match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
            if match:
                return content[match.end():].strip()
        return content

    def _parse_nanobot_metadata(self, raw: str) -> dict:
        """
        解析 nanobot 元数据

        从 frontmatter 的 metadata 字段中提取 nanobot 配置。

        参数:
            raw: metadata 字段的原始值（JSON 字符串）

        返回:
            nanobot 元数据字典

        示例:
            raw = '{"nanobot": {"emoji": "🐙", "requires": {"bins": ["gh"]}}}'
            result = {"emoji": "🐙", "requires": {"bins": ["gh"]}}
        """
        try:
            data = json.loads(raw)
            return data.get("nanobot", {}) if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _check_requirements(self, skill_meta: dict) -> bool:
        """
        检查技能依赖是否满足

        检查所需的命令行工具和环境变量是否存在。

        参数:
            skill_meta: 技能元数据

        返回:
            True 如果所有依赖都满足，否则 False

        依赖检查：
        1. bins: 命令行工具（使用 shutil.which() 检查）
        2. env: 环境变量（使用 os.environ.get() 检查）
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

        从 frontmatter 中提取并解析 nanobot 配置。

        参数:
            name: 技能名称

        返回:
            nanobot 元数据字典
        """
        meta = self.get_skill_metadata(name) or {}
        return self._parse_nanobot_metadata(meta.get("metadata", ""))

    def get_always_skills(self) -> list[str]:
        """
        获取始终加载的技能列表

        返回标记为 always_load=true 且依赖满足的技能。
        这些技能的完整内容会被加载到 Agent 上下文中。

        返回:
            技能名称列表

        示例:
            ["github", "weather"]  # 这些技能会始终加载
        """
        result = []
        for s in self.list_skills(filter_unavailable=True):
            meta = self.get_skill_metadata(s["name"]) or {}
            skill_meta = self._parse_nanobot_metadata(meta.get("metadata", ""))

            # 检查 always 或 always_load 标记
            if skill_meta.get("always") or meta.get("always"):
                result.append(s["name"])

        return result

    def get_skill_metadata(self, name: str) -> dict | None:
        """
        获取技能的 frontmatter 元数据

        解析 SKILL.md 文件开头的 YAML frontmatter。

        参数:
            name: 技能名称

        返回:
            元数据字典，如果未找到返回 None

        Frontmatter 格式：
            ---
            name: github
            description: "使用 gh CLI 与 GitHub 交互"
            metadata: {"nanobot": {...}}
            ---

        注意：这是简化的 YAML 解析，仅支持简单的 key: value 格式。
        """
        content = self.load_skill(name)
        if not content:
            return None

        if content.startswith("---"):
            # 匹配 frontmatter
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
