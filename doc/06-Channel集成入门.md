# 阶段 6: Channel 集成入门

**难度**: ⭐⭐⭐
**预计时间**: 3-5 天

## 🎯 学习目标

- ✅ 理解 Channel 基类和消息流
- ✅ 集成 Telegram 或 Discord
- ✅ 实现多用户对话管理
- ✅ 配置访问控制（allowFrom）

## 📖 Channel 架构

### BaseChannel 接口

```python
class BaseChannel(ABC):
    async def start(self):
        """启动频道"""
    
    async def stop(self):
        """停止频道"""
    
    async def send_message(self, chat_id: str, content: str):
        """发送消息"""
```

### 消息流程

```
平台消息 → Channel → InboundMessage → Bus → Agent
Agent → OutboundMessage → Bus → Channel → 平台消息
```

## 🚀 Telegram 集成实践

### 步骤 1: 创建 Bot

1. 在 Telegram 找到 @BotFather
2. 发送 `/newbot` 创建机器人
3. 获取 token

### 步骤 2: 配置

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "你的token",
      "allowFrom": ["你的用户ID"]
    }
  }
}
```

### 步骤 3: 启动

```bash
nanobot gateway
```

## 📝 实践任务

- [ ] 集成至少一个 Channel
- [ ] 测试多用户对话
- [ ] 配置访问控制
- [ ] 处理媒体消息

## 🎉 完成！

进入 [阶段 7: 消息总线与架构](./07-消息总线与架构.md)
