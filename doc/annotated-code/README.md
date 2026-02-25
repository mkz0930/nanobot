# nanobot 核心代码详细注释

本目录包含 nanobot 所有 10 个学习阶段的核心代码文件，带有详细的中文注释。

---

## 📚 快速导航

### 🎯 推荐阅读顺序
1. **[快速参考.md](快速参考.md)** ⭐ 快速查找核心概念和代码模式
2. **[核心代码注释索引.md](核心代码注释索引.md)** ⭐ 完整的学习指南
3. **具体注释文件** - 深入学习每个组件
4. **[完成总结.md](完成总结.md)** - 学习建议和下一步

### 📖 核心文档
- **[快速参考.md](快速参考.md)** - 核心组件速查、常用代码模式、数据流速查
- **[核心代码注释索引.md](核心代码注释索引.md)** - 所有 5 个阶段的完整学习指南
- **[完成总结.md](完成总结.md)** - 已完成工作总结和学习建议

---

## 📁 已完成的注释文件

### ✅ 阶段 1-2: 核心架构
**[01-events.py](01-events.py)** - 消息总线事件定义
- InboundMessage 和 OutboundMessage 详细注释
- session_key 的作用说明
- 消息流程图

**[02-context.py](02-context.py)** - 上下文构建器
- 系统提示构建流程
- 渐进式技能加载策略
- 多模态内容处理（文本+图片）
- 工具结果和助手消息管理

**[03-loop.py](03-loop.py)** - Agent 主循环
- 完整的消息处理流程
- Agent 循环的迭代逻辑
- 工具调用执行机制
- 会话管理和上下文更新

### ✅ 阶段 3: 工具系统
**[05-tool-base.py](05-tool-base.py)** - 工具抽象基类
- Tool 基类的完整实现
- JSON Schema 参数验证详解
- 为什么返回字符串的设计理念
- 完整的使用示例

**[06-filesystem.py](06-filesystem.py)** - 文件系统工具
- ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
- 沙箱模式和路径限制
- 错误处理和安全检查

**[07-shell.py](07-shell.py)** - Shell 执行工具
- 命令执行和输出捕获
- 危险命令检测（黑名单）
- 超时控制和沙箱限制

### ✅ 阶段 4: 技能系统
**[08-skills.py](08-skills.py)** - 技能加载器
- 技能扫描和加载机制
- 渐进式加载策略
- 依赖检查（bins, env）
- Frontmatter 元数据解析

### ✅ 阶段 5: Provider 系统
**[09-registry.py](09-registry.py)** - Provider 注册表
- ProviderSpec 数据类详解
- 所有字段的详细说明
- 网关型、标准型、本地型 Provider 的区别
- 模型前缀自动处理逻辑

**[10-litellm-provider.py](10-litellm-provider.py)** - LiteLLM Provider 实现
- 多 Provider 统一接口
- 模型名解析和前缀处理
- 环境变量自动配置
- 工具调用和响应解析

### ✅ 阶段 6: Channel 集成
**[11-base-channel.py](11-base-channel.py)** - Channel 基类
- 统一的聊天平台接口
- 消息接收和发送流程
- 访问控制（allowFrom 白名单）
- 实现指南和最佳实践

### ✅ 阶段 7: 消息总线
**[12-message-bus.py](12-message-bus.py)** - 消息总线
- 发布-订阅模式实现
- 异步消息队列机制
- 消息分发和路由
- 解耦 Channel 和 Agent

### ✅ 阶段 8-9: 高级功能与会话管理
**[13-session-manager.py](13-session-manager.py)** - 会话管理器
- 多用户对话历史管理
- JSONL 格式持久化
- 内存缓存优化
- 会话加载和保存

**[14-memory-store.py](14-memory-store.py)** - 记忆系统
- 长期记忆（MEMORY.md）
- 日记系统（每日记录）
- 记忆上下文构建
- Agent 记忆管理

---

## 🎯 使用说明

### 学习路径
```
1. 阅读学习文档 (doc/0X-xxx.md)
   ↓
2. 阅读快速参考 (快速参考.md)
   ↓
3. 阅读核心代码注释索引 (核心代码注释索引.md)
   ↓
4. 阅读具体注释文件 (01-events.py 等)
   ↓
5. 查看原始代码 (nanobot/ 目录)
   ↓
6. 实践练习
```

### 如何使用

1. **快速查阅** - 打开 [快速参考.md](快速参考.md)
2. **系统学习** - 阅读 [核心代码注释索引.md](核心代码注释索引.md)
3. **深入理解** - 阅读具体注释文件
4. **对照学习** - 结合学习文档和注释代码
5. **实践验证** - 在 IDE 中调试原始代码

---

## 📊 注释统计

- **总文件数**: 14 个核心文件
- **总注释行数**: 约 5000+ 行
- **覆盖阶段**: 阶段 1-9（完整）
- **注释类型**: 模块、类、方法、字段、行内
- **注释风格**: 小白友好，详细解释设计思路和实现细节

## 📋 覆盖的核心模块

### 核心架构（阶段 1-2）
- ✅ 消息事件定义
- ✅ 上下文构建器
- ✅ Agent 主循环

### 工具系统（阶段 3）
- ✅ 工具基类和注册表
- ✅ 文件系统工具
- ✅ Shell 执行工具

### 技能系统（阶段 4）
- ✅ 技能加载器
- ✅ 渐进式加载机制

### Provider 系统（阶段 5）
- ✅ Provider 注册表
- ✅ LiteLLM Provider 实现

### Channel 系统（阶段 6）
- ✅ Channel 基类
- ✅ 消息接收和发送

### 消息总线（阶段 7）
- ✅ 异步消息队列
- ✅ 发布-订阅模式

### 高级功能（阶段 8-9）
- ✅ 会话管理器
- ✅ 记忆系统

---

## 🔗 相关资源

### 学习文档
- [学习路线图](../00-学习路线图.md)
- [阶段 1-5 学习文档](../)

### 官方资源
- [GitHub 仓库](https://github.com/mkz0930/nanobot)
- [README.md](../../README.md)
- [CLAUDE.md](../../CLAUDE.md)

### 社区
- [Discord 社区](https://discord.gg/MnCvHqpUGB)
- [GitHub Issues](https://github.com/mkz0930/nanobot/issues)

---

**祝学习愉快！** 🎉
