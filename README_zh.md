![AstrBot-Logo-Simplified](https://github.com/user-attachments/assets/ffd99b6b-3272-4682-beaa-6fe74250f7d9)

<div align="center">

<a href="./README.md">English</a> ｜
<a href="./README_zh.md">简体中文</a>

<div>
<img src="https://img.shields.io/github/v/release/Xero-Team/AstrBot?color=76bad9" href="https://github.com/Xero-Team/AstrBot/releases/latest">
<img src="https://img.shields.io/badge/python-3.14+-blue.svg" alt="python">
</div>

<br>

<a href="https://astrbot.app/">主页</a> ｜
<a href="https://astrbot.app/">文档</a> ｜
<a href="https://github.com/Xero-Team/AstrBot/issues">问题提交</a> ｜
<a href="mailto:community@astrbot.app">Email</a>

</div>

AstrBot 是一个开源的一站式 Agentic 个人和群聊助手，可在 QQ、Telegram、企业微信、飞书、钉钉、Slack 等数十款主流即时通讯软件上部署，此外还内置类似 OpenWebUI 的轻量化 ChatUI，为个人、开发者和团队打造可靠、可扩展的对话式智能基础设施。无论是个人 AI 伙伴、智能客服、自动化助手，还是企业知识库，AstrBot 都能在你的即时通讯软件平台的工作流中快速构建 AI 应用。

这个仓库是 AstrBot 的现代化 fork。这里记录的命令、部署文件和兼容性边界均以当前分支为准：Python 3.14+、后端使用 `uv`、前端使用 `corepack pnpm`，并且不再为旧兼容路径背书。

![landingpage](https://github.com/user-attachments/assets/45fc5699-cddf-4e21-af35-13040706f6c0)

## 主要功能

1. 💯 免费 & 开源。
2. ✨ AI 大模型对话，多模态，Agent，MCP，Skills，知识库，人格设定，自动压缩对话。
3. 🤖 支持接入 Dify、阿里云百炼、Coze 等智能体平台。
4. 🌐 多平台，支持 QQ、企业微信、飞书、钉钉、微信公众号、Telegram、Slack 以及[更多](#支持的消息平台)。
5. 📦 插件扩展，已有 1000+ 个插件可一键安装。
6. 🛡️ [Agent Sandbox](https://docs.astrbot.app/use/astrbot-agent-sandbox.html) 隔离化环境，安全地执行任何代码、调用 Shell、会话级资源复用。
7. 💻 WebUI 支持。
8. 🌈 Web ChatUI 支持，ChatUI 内置代理沙盒、网页搜索等。
9. 🌐 WebUI 双语：简体中文和英文。

<br>

<table align="center">
  <tr align="center">
    <th>💙 角色扮演 & 情感陪伴</th>
    <th>✨ 主动式 Agent</th>
    <th>🚀 通用 Agentic 能力</th>
    <th>🧩 1000+ 社区插件</th>
  </tr>
  <tr>
    <td align="center"><p align="center"><img width="984" height="1746" alt="99b587c5d35eea09d84f33e6cf6cfd4f" src="https://github.com/user-attachments/assets/89196061-3290-458d-b51f-afa178049f84" /></p></td>
    <td align="center"><p align="center"><img width="976" height="1612" alt="c449acd838c41d0915cc08a3824025b1" src="https://github.com/user-attachments/assets/f75368b4-e022-41dc-a9e0-131c3e73e32e" /></p></td>
    <td align="center"><p align="center"><img width="974" height="1732" alt="image" src="https://github.com/user-attachments/assets/e22a3968-87d7-4708-a7cd-e7f198c7c32e" /></p></td>
    <td align="center"><p align="center"><img width="976" height="1734" alt="image" src="https://github.com/user-attachments/assets/0952b395-6b4a-432a-8a50-c294b7f89750" /></p></td>
  </tr>
</table>

## 快速开始

### `uv` 安装

如需直接在本机安装运行，使用 `uv`：

```bash
uv tool install astrbot --python 3.14
astrbot init # 仅首次执行此命令以初始化环境
astrbot run
```

> 需要安装 [uv](https://docs.astral.sh/uv/)。
> AstrBot 需要 Python 3.14 或更高版本。`--python 3.14` 会确保 `uv` 使用 Python 3.14 创建 tool 环境。

> [!NOTE]
> 对于 macOS 用户：由于 macOS 安全检查，首次运行 `astrbot` 命令可能需要较长时间（约 10-20 秒）。

更新 `astrbot`：

```bash
uv tool upgrade astrbot --python 3.14
```

> [!WARNING]
> 通过 `uv` 部署的 AstrBot **不支持在 WebUI 中进行版本升级**。如需更新，请通过命令行执行上述命令。

### Docker 部署

当前 fork 不提供官方预构建镜像，请直接使用仓库内的 Compose 文件本地构建并启动：

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
docker compose up -d --build
```

如果希望一并拉起 AstrBot 和 NapCat：

```bash
docker compose -f compose-with-napcat.yml up -d --build
```

更多细节请参考 [使用 Docker 部署 AstrBot](https://docs.astrbot.app/deploy/astrbot/docker.html#%E4%BD%BF%E7%94%A8-docker-%E9%83%A8%E7%BD%B2-astrbot)。

### AUR

AUR 方式面向 Arch Linux 用户，适合希望通过系统包管理器安装 AstrBot 的场景。

在终端执行下方命令安装 `astrbot-git` 包，安装完成后即可启动使用。

```bash
yay -S astrbot-git
```

如果你要从源码本地开发，请看下面的开发环境章节。

## 支持的消息平台

将 AstrBot 连接到你常用的聊天平台。

| 平台                                                                                  | 维护方   |
| ------------------------------------------------------------------------------------- | -------- |
| **QQ**                                                                                | 官方维护 |
| **OneBot v11**                                                                        | 官方维护 |
| **Telegram**                                                                          | 官方维护 |
| **企微应用 & 企微智能机器人**                                                         | 官方维护 |
| **微信客服 & 微信公众号**                                                             | 官方维护 |
| **个人微信**                                                                          | 官方维护 |
| **飞书**                                                                              | 官方维护 |
| **钉钉**                                                                              | 官方维护 |
| **Slack**                                                                             | 官方维护 |
| **Discord**                                                                           | 官方维护 |
| **LINE**                                                                              | 官方维护 |
| **Satori**                                                                            | 官方维护 |
| **KOOK**                                                                              | 官方维护 |
| **Misskey**                                                                           | 官方维护 |
| **Mattermost**                                                                        | 官方维护 |
| **WhatsApp（将支持）**                                                                | 官方维护 |
| [**Matrix**](https://github.com/stevessr/astrbot_plugin_matrix_adapter)               | 社区维护 |
| [**Rocket.Chat**](https://github.com/NET-Homeless/astrbot_plugin_rocket_chat_adapter) | 社区维护 |
| [**VoceChat**](https://github.com/HikariFroya/astrbot_plugin_vocechat)                | 社区维护 |

## 支持的模型提供商

| 服务类型              | 内置选项                                                                                                                      |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 对话 / LLM            | OpenAI 兼容服务、OpenAI、Anthropic、Gemini、Moonshot、智谱、DeepSeek                                                          |
| 本地 LLM              | Ollama、LM Studio                                                                                                             |
| Agent 执行器          | Dify、Coze、阿里云百炼应用、DeerFlow                                                                                          |
| 语音转文本            | OpenAI Whisper、SenseVoice、Xiaomi MiMo Omni                                                                                  |
| 文本转语音            | OpenAI TTS、Gemini TTS、GPT-SoVITS、FishAudio、Edge TTS、Azure TTS、Minimax TTS、火山引擎 TTS、ElevenLabs TTS、阿里云百炼 TTS |
| Embedding / Rerank 等 | 以 WebUI 中当前可选提供商列表为准                                                                                             |

## ❤️ 贡献

欢迎任何 Issues/Pull Requests！只需要将你的更改提交到此项目 ：)

### 如何贡献

你可以通过查看问题或帮助审核 PR（拉取请求）来贡献。任何问题或 PR 都欢迎参与，以促进社区贡献。当然，这些只是建议，你可以以任何方式进行贡献。对于新功能的添加，请先通过 Issue 讨论。

### 开发环境

AstrBot 使用 `ruff` 进行代码格式化和检查。

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
make doctor
make bootstrap
pip install pre-commit
pre-commit install
```

Linux 下完整的工具安装、开发服务、日志、检查与 NapCat 代码生成流程请参阅
[Linux 开发环境](docs/zh/dev/linux.md)。

## 🌍 社区

### QQ 群组

- 1 群：322154837 (人满)
- 3 群：630166526 (人满)
- 4 群：1077826412 (人满)
- 5 群：822130018 (人满)
- 6 群：753075035 (人满)
- 7 群：743746109 (人满)
- 8 群：1030353265 (人满)
- 9 群：1076659624 (人满)
- 10 群：1078079676 (人满)
- 11 群：704659519 (人满)
- 12 群：916228568 (人满)
- 13 群：1092185289
- 14 群：1103419483

- 开发者群（偏闲聊吹水）：975206796
- 开发者群（正式）：1039761811

### Discord 频道

- [Discord](https://discord.gg/hAVk6tgV36)

## ❤️ Special Thanks

特别感谢所有 Contributors 和插件开发者对 AstrBot 的贡献 ❤️

<a href="https://github.com/Xero-Team/AstrBot/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Xero-Team/AstrBot&max=300&columns=15" />
</a>

此外，本项目的诞生离不开以下开源项目的帮助：

- [NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ) - 伟大的猫猫框架

开源项目友情链接：

- [NoneBot2](https://github.com/nonebot/nonebot2) - 优秀的 Python 异步 ChatBot 框架
- [Koishi](https://github.com/koishijs/koishi) - 优秀的 Node.js ChatBot 框架
- [MaiBot](https://github.com/Mai-with-u/MaiBot) - 优秀的拟人化 AI ChatBot
- [nekro-agent](https://github.com/KroMiose/nekro-agent) - 优秀的 Agent ChatBot
- [LangBot](https://github.com/langbot-app/LangBot) - 优秀的多平台 AI ChatBot
- [ChatLuna](https://github.com/ChatLunaLab/chatluna) - 优秀的多平台 AI ChatBot Koishi 插件
- [Operit AI](https://github.com/AAswordman/Operit) - 优秀的 AI 智能助手 Android APP

## ⭐ Star History

> [!TIP]
> 如果本项目对您的生活 / 工作产生了帮助，或者您关注本项目的未来发展，请给项目 Star，这是我们维护这个开源项目的动力 <3

<div align="center">

[![Star History Chart](https://api.star-history.com/svg?repos=begoniahe/astrbot&type=Date)](https://star-history.com/#begoniahe/astrbot&Date)

</div>

<div align="center">

_陪伴与能力从来不应该是对立面。我们希望创造的是一个既能理解情绪、给予陪伴，也能可靠完成工作的机器人。_

_私は、高性能ですから!_

<img src="https://files.astrbot.app/watashiwa-koseino-desukara.gif" width="100"/>

</div>
