# feishu-codex-cli

A lightweight local bridge between Feishu and Codex CLI.

一个轻量的本地 Feishu <-> Codex CLI 中继服务。

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
[![Release](https://img.shields.io/github/v/tag/wszrw123/feishu-codex-cli?label=release)](https://github.com/wszrw123/feishu-codex-cli/tags)

## Overview

`feishu-codex-cli` is designed for a simple workflow: receive messages from one Feishu group chat, run Codex CLI locally, and send the response back with minimal runtime overhead.

`feishu-codex-cli` 适合这种简单场景：从单个飞书群读取消息，在本地调用 Codex CLI，再把结果回发到群里，同时尽量保持运行时和上下文开销可控。

## Features

- Polls messages from a single Feishu `chat_id`
- Runs Codex CLI locally inside your chosen workspace
- Keeps conversation context intentionally small
- Disables `resume` by default for diagnostic-style requests
- Records token usage and elapsed time for each Codex run
- Supports custom `OPENAI_BASE_URL` when needed

- 支持单个飞书 `chat_id` 轮询收消息
- 在指定工作目录中本地运行 Codex CLI
- 默认采用轻量上下文，减少会话膨胀
- 遇到诊断类请求时默认不走 `resume`
- 记录每次 Codex 调用的 token 用量和耗时
- 支持按需配置 `OPENAI_BASE_URL`

## Use Cases

- Personal coding assistant inside a Feishu group chat
- A lightweight alternative to heavier relay stacks
- Workspace-local automation with explicit context limits

- 在飞书群里使用个人编码助手
- 作为更重型中继方案的轻量替代
- 用于本地工作区自动化，并显式限制上下文膨胀

## Requirements

- Python 3.10+
- Codex CLI installed and available in `PATH`
- A Feishu app with permission to read and send group messages
- A target Feishu group `chat_id`

- Python 3.10+
- 已安装并可执行的 Codex CLI
- 具备群消息读取和发送权限的飞书应用
- 目标飞书群的 `chat_id`

## Files

- `service.py`: main service process / 主服务进程
- `start-feishu-codex.sh`: startup script / 启动脚本
- `config.example.json`: config template / 配置模板
- `.runtime/`: runtime logs and local state / 运行日志和本地状态目录

## Quick Start

### 1. Prepare config

```bash
cp config.example.json .feishu-codex-cli.config.local.json
```

Fill in `.feishu-codex-cli.config.local.json` with your own values:

在 `.feishu-codex-cli.config.local.json` 中填写你自己的配置：

- `feishuAppId`
- `feishuAppSecret`
- `feishuChatId`
- `codexWorkdir`
- `openaiApiKey` or leave it empty to rely on your Codex environment
- `openaiBaseUrl` if you use a custom endpoint

### 2. Start the service

```bash
./start-feishu-codex.sh
```

### 3. Verify runtime output

Check `.runtime/service.log` if the service starts but does not reply as expected.

如果服务启动了但没有正常回复，优先查看 `.runtime/service.log`。

## Configuration Notes

- `codexCliPath`: path to the Codex CLI binary, or simply `codex` if it is already in `PATH`
- `codexWorkdir`: the workspace where Codex CLI should run
- `codexSandboxMode`: sandbox mode passed to Codex CLI
- `codexSkipGitRepoCheck`: whether to skip repo validation in local workflows
- `replyMaxChars`: max Feishu reply length after clipping

- `codexCliPath`：Codex CLI 可执行文件路径；如果已在 `PATH` 中可直接写 `codex`
- `codexWorkdir`：Codex CLI 运行的工作目录
- `codexSandboxMode`：传给 Codex CLI 的沙箱模式
- `codexSkipGitRepoCheck`：本地工作流中是否跳过仓库检查
- `replyMaxChars`：飞书回复的最大裁剪长度

See [config.example.json](./config.example.json) for the full template.

完整配置项请参考 [config.example.json](./config.example.json)。

## Context Control Strategy

To keep the bridge responsive over long conversations, the service uses a few guardrails:

为了在长对话中保持响应速度，服务做了几层上下文控制：

- Only recent events are kept in the active session
- A short summary is generated for older context
- Diagnostic requests start a fresh Codex execution path
- Sessions rotate automatically when token usage or elapsed time gets too large

- 活跃会话只保留最近少量事件
- 更早的上下文会被压缩成短摘要
- 诊断类请求会优先走新的 Codex 执行流程
- 当 token 或耗时过大时会自动轮换会话

## Suggested Workflow

- Keep one Feishu group dedicated to one workspace or project
- Use short task-oriented prompts for better reply quality
- Let the bridge rotate sessions when conversations become too large

- 一个飞书群最好只对应一个工作区或项目
- 任务型短提示词通常能获得更稳定的回复
- 当会话变大时，让服务自动轮换 session 会更稳妥

## Privacy

The sample config intentionally leaves secrets blank and uses placeholder paths. Do not commit `.feishu-codex-cli.config.local.json` or runtime files.

示例配置故意留空密钥并使用占位路径。请不要提交 `.feishu-codex-cli.config.local.json` 和运行时文件。

## License

Released under the MIT License.

基于 MIT License 开源。
