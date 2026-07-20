![AstrBot-Logo-Simplified](https://github.com/user-attachments/assets/ffd99b6b-3272-4682-beaa-6fe74250f7d9)

<div align="center">

<a href="./README.md">English</a> ｜
<a href="./README_zh.md">简体中文</a>

<br>

<div>
<img src="https://img.shields.io/github/v/release/Xero-Team/AstrBot?color=76bad9" href="https://github.com/Xero-Team/AstrBot/releases/latest">
<img src="https://img.shields.io/badge/python-3.14+-blue.svg" alt="python">
</div>

<br>

<a href="https://astrbot.app/">Documentation</a> ｜
<a href="https://github.com/Xero-Team/AstrBot/issues">Issue Tracker</a> ｜
<a href="mailto:community@astrbot.app">Email Support</a>

</div>

AstrBot is an open-source all-in-one Agent chatbot platform that integrates with mainstream instant messaging apps. It provides reliable and scalable conversational AI infrastructure for individuals, developers, and teams. Whether you're building a personal AI companion, intelligent customer service, automation assistant, or enterprise knowledge base, AstrBot enables you to quickly build production-ready AI applications within your IM platform workflows.

This repository is a modernized fork of AstrBot. The code, commands, deployment files, and compatibility expectations documented here describe this fork only: Python 3.14+, `uv` for backend workflows, `corepack pnpm` for the dashboard, and no legacy compatibility shims.

![screenshot_1 5x_postspark_2026-02-27_22-37-45](https://github.com/user-attachments/assets/f17cdb90-52d7-4773-be2e-ff64b566af6b)

## Key Features

1. 💯 Free & Open Source.
2. ✨ AI LLM Conversations, Multimodal, Agent, MCP, Skills, Knowledge Base, Persona Settings, Auto Context Compression.
3. 🤖 Supports integration with Dify, Alibaba Cloud Bailian, Coze, and other agent platforms.
4. 🌐 Multi-Platform: QQ, WeChat Work, Feishu, DingTalk, WeChat Official Accounts, Telegram, Slack, and [more](#supported-messaging-platforms).
5. 📦 Plugin Extensions with 1000+ plugins available for one-click installation.
6. 🛡️ [Agent Sandbox](https://docs.astrbot.app/use/astrbot-agent-sandbox.html) for isolated, safe execution of code, shell calls, and session-level resource reuse.
7. 💻 WebUI Support.
8. 🌈 Web ChatUI Support with built-in agent sandbox and web search.
9. 🌐 Bilingual WebUI: Simplified Chinese and English.

<br>

<table align="center">
  <tr align="center">
    <th>💙 Role-playing & Emotional Companionship</th>
    <th>✨ Proactive Agent</th>
    <th>🚀 General Agentic Capabilities</th>
    <th>🧩 1000+ Community Plugins</th>
  </tr>
  <tr>
    <td align="center"><p align="center"><img width="984" height="1746" alt="99b587c5d35eea09d84f33e6cf6cfd4f" src="https://github.com/user-attachments/assets/89196061-3290-458d-b51f-afa178049f84" /></p></td>
    <td align="center"><p align="center"><img width="976" height="1612" alt="c449acd838c41d0915cc08a3824025b1" src="https://github.com/user-attachments/assets/f75368b4-e022-41dc-a9e0-131c3e73e32e" /></p></td>
    <td align="center"><p align="center"><img width="974" height="1732" alt="image" src="https://github.com/user-attachments/assets/e22a3968-87d7-4708-a7cd-e7f198c7c32e" /></p></td>
    <td align="center"><p align="center"><img width="976" height="1734" alt="image" src="https://github.com/user-attachments/assets/0952b395-6b4a-432a-8a50-c294b7f89750" /></p></td>
  </tr>
</table>

## Quick Start

### `uv` Install

For a direct local install, use `uv`:

```bash
uv tool install astrbot --python 3.14
astrbot init # Only execute this command for the first time to initialize the environment
astrbot run
```

> Requires [uv](https://docs.astral.sh/uv/) to be installed.
> AstrBot requires Python 3.14 or later. The `--python 3.14` option ensures that `uv` creates the tool environment with Python 3.14.

> [!NOTE]
> For macOS users: due to macOS security checks, the first run of the `astrbot` command may take longer (about 10-20s).

Update `astrbot`:

```bash
uv tool upgrade astrbot --python 3.14
```

> [!WARNING]
> AstrBot deployed via `uv` **does not support upgrading through the WebUI**. To update, please run the command above from the command line.

### Docker Deployment

This fork does not publish an official prebuilt image. Build and run from the compose files in this repository:

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
docker compose up -d --build
```

If you want to start AstrBot and NapCat together from this repository:

```bash
docker compose -f compose-with-napcat.yml up -d --build
```

More details: [Deploy AstrBot with Docker](https://docs.astrbot.app/deploy/astrbot/docker.html).

### AUR

AUR deployment targets Arch Linux users who prefer installing AstrBot through the system package workflow.

Run the command below to install `astrbot-git`, then start AstrBot in your local environment.

```bash
yay -S astrbot-git
```

For source-based local development, see the development environment section below.

## Supported Messaging Platforms

Connect AstrBot to your favorite chat platform.

| Platform                                                                          | Maintainer |
| --------------------------------------------------------------------------------- | ---------- |
| QQ                                                                                | Official   |
| OneBot v11 protocol implementation                                                | Official   |
| Telegram                                                                          | Official   |
| Wecom & Wecom AI Bot                                                              | Official   |
| WeChat Official Accounts                                                          | Official   |
| Personal WeChat                                                                   | Official   |
| Feishu (Lark)                                                                     | Official   |
| DingTalk                                                                          | Official   |
| Slack                                                                             | Official   |
| Discord                                                                           | Official   |
| LINE                                                                              | Official   |
| Satori                                                                            | Official   |
| KOOK                                                                              | Official   |
| Misskey                                                                           | Official   |
| Mattermost                                                                        | Official   |
| WhatsApp (Coming Soon)                                                            | Official   |
| [Matrix](https://github.com/stevessr/astrbot_plugin_matrix_adapter)               | Community  |
| [Rocket.Chat](https://github.com/NET-Homeless/astrbot_plugin_rocket_chat_adapter) | Community  |
| [VoceChat](https://github.com/HikariFroya/astrbot_plugin_vocechat)                | Community  |

## Supported Model Services

| Service Type                | Built-in Options                                                                                                               |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Conversation / LLM          | OpenAI-compatible services, OpenAI, Anthropic, Gemini, Moonshot, Zhipu, DeepSeek                                               |
| Local LLM                   | Ollama, LM Studio                                                                                                              |
| Agent Runners               | Dify, Coze, Alibaba Cloud Bailian applications, DeerFlow                                                                       |
| Speech-to-Text              | OpenAI Whisper, SenseVoice, Xiaomi MiMo Omni                                                                                   |
| Text-to-Speech              | OpenAI TTS, Gemini TTS, GPT-SoVITS, FishAudio, Edge TTS, Azure TTS, Minimax TTS, Volcengine TTS, ElevenLabs TTS, Dashscope TTS |
| Embedding / Rerank / Others | See the provider list in WebUI for the current built-in set                                                                    |

## ❤️ Contributing

Issues and Pull Requests are always welcome. Please target this fork's repository and keep documentation aligned with the current branch behavior rather than upstream historical behavior.

### How to Contribute

You can contribute by reviewing issues or helping with pull request reviews. Any issues or PRs are welcome to encourage community participation. Of course, these are just suggestions—you can contribute in any way you like. For adding new features, please discuss through an Issue first.

### Development Environment

AstrBot uses `ruff` for code formatting and linting.

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
make doctor
make bootstrap
pip install pre-commit
pre-commit install
```

For the complete Linux workflow, including tool installation, development
servers, logs, checks, and NapCat code generation, see [Linux Development](docs/en/dev/linux.md).

## 🌍 Community

### QQ Groups

- Group 1: 322154837 (Full)
- Group 3: 630166526 (Full)
- Group 4: 1077826412 (Full)
- Group 5: 822130018 (Full)
- Group 6: 753075035 (Full)
- Group 7: 743746109 (Full)
- Group 8: 1030353265 (Full)
- Group 9: 1076659624 (Full)
- Group 10: 1078079676 (Full)
- Group 11: 704659519 (Full)
- Group 12: 916228568 (Full)
- Group 13: 1092185289
- Group 14: 1103419483

- Developer Group(Chit-chat): 975206796
- Developer Group(Formal): 1039761811

### Discord Server

<a href="https://discord.gg/hAVk6tgV36"><img alt="Discord_community" src="https://img.shields.io/badge/Discord-AstrBot-purple?style=for-the-badge&color=76bad9"></a>

## ❤️ Special Thanks

Special thanks to all Contributors and plugin developers for their contributions to AstrBot ❤️

<a href="https://github.com/Xero-Team/AstrBot/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Xero-Team/AstrBot&max=300&columns=15" />
</a>

Additionally, the birth of this project would not have been possible without the help of the following open-source projects:

- [NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ) - The amazing cat framework

## ⭐ Star History

> [!TIP]
> If this project has helped you in your life or work, or if you're interested in its future development, please give the project a Star. It's the driving force behind maintaining this open-source project <3

<div align="center">

[![Star History Chart](https://api.star-history.com/svg?repos=begoniahe/astrbot&type=Date)](https://star-history.com/#begoniahe/astrbot&Date)

</div>

<div align="center">

_Companionship and capability should never be at odds. What we aim to create is a robot that can understand emotions, provide genuine companionship, and reliably accomplish tasks._

_私は、高性能ですから!_

<img src="https://files.astrbot.app/watashiwa-koseino-desukara.gif" width="100"/>
</div>
