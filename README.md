# feishu-codex-cli

一个比 `xcode-tg` 更轻的本地 Feishu <-> Codex CLI 中继。

目标：

- 只保留 Feishu 与 Codex CLI 通信能力
- 默认控制上下文膨胀
- 不依赖 OpenClaw runtime
- 适合本机工作区驱动的日常使用

## 特性

- 飞书群轮询收消息，支持单个 `chat_id`
- 本地调用 `codex cli`
- 默认轻量上下文：短摘要、有限事件、有限输出
- 诊断型请求默认禁用 `resume`
- 自动记录 `input_tokens` / `cached_input_tokens` / `output_tokens`
- 支持自定义 `OPENAI_BASE_URL`，兼容中转地址

## 目录

- `service.py`: 主服务
- `start-feishu-codex.sh`: 启动脚本
- `config.example.json`: 配置模板
- `.runtime/`: 运行时日志、状态、上下文缓存

## 快速开始

```bash
cd /Users/zhengrongwei/Desktop/person/feishu-codex-cli
cp config.example.json .feishu-codex-cli.config.local.json
```

编辑 `.feishu-codex-cli.config.local.json`，填入：

- `feishuAppId`
- `feishuAppSecret`
- `feishuChatId`
- `codexWorkdir`
- `openaiBaseUrl` 或保持为空沿用 `~/.codex/config.toml`

启动：

```bash
./start-feishu-codex.sh
```

## 设计上的防膨胀策略

- 普通消息才允许尝试 `resume`
- 命中诊断关键词时，强制 `exec_new`
- 只缓存最近少量会话事件，并生成短摘要
- Prompt 明确要求先小范围读日志，不要整段读大文件
- 当上一轮 `input_tokens` 或耗时过大时，自动丢弃旧 session

## 配置说明

参考 [config.example.json](/Users/zhengrongwei/Desktop/person/feishu-codex-cli/config.example.json)。
