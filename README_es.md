![AstrBot-Logo-Simplified](https://github.com/user-attachments/assets/ffd99b6b-3272-4682-beaa-6fe74250f7d9)

<div align="center">

<a href="./README_zh.md">简体中文</a> ｜
<a href="./README.md">English</a> ｜
<a href="./README_zh-TW.md">繁體中文</a> ｜
<a href="./README_ja.md">日本語</a> ｜
<a href="./README_fr.md">Français</a> ｜
<a href="./README_ru.md">Русский</a>

<br>

<div>
<img src="https://img.shields.io/github/v/release/BegoniaHe/AstrBot?color=76bad9" href="https://github.com/BegoniaHe/AstrBot/releases/latest">
<img src="https://img.shields.io/badge/python-3.14+-blue.svg" alt="python">
<a href="https://hub.docker.com/r/soulter/astrbot"><img alt="Docker pull" src="https://img.shields.io/docker/pulls/soulter/astrbot.svg?color=76bad9"/></a>
<img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fapi.soulter.top%2Fastrbot%2Fplugin-num&query=%24.result&suffix=%20plugins&label=Marketplace&cacheSeconds=3600">
</div>

<br>

<a href="https://astrbot.app/">Documentación</a> ｜
<a href="https://blog.astrbot.app/">Blog</a> ｜
<a href="https://astrbot.featurebase.app/roadmap">Hoja de ruta</a> ｜
<a href="https://github.com/BegoniaHe/AstrBot/issues">Registro de incidencias</a> ｜
<a href="mailto:community@astrbot.app">Soporte por correo</a>

</div>

AstrBot es una plataforma de chatbot Agent todo en uno de código abierto que se integra con las principales aplicaciones de mensajería instantánea. Proporciona una infraestructura de IA conversacional confiable y escalable para individuos, desarrolladores y equipos. Ya sea que estés construyendo un compañero de IA personal, un servicio de atención al cliente inteligente, un asistente de automatización o una base de conocimiento empresarial, AstrBot te permite crear rápidamente aplicaciones de IA listas para producción dentro de los flujos de trabajo de tu plataforma de mensajería instantánea.

Este repositorio es un fork modernizado de AstrBot. El código, los comandos, los archivos de despliegue y los límites de compatibilidad documentados aquí describen solo esta rama: Python 3.14+, `uv` para el backend, `corepack pnpm` para el dashboard y sin capas de compatibilidad heredadas.

![screenshot_1 5x_postspark_2026-02-27_22-37-45](https://github.com/user-attachments/assets/f17cdb90-52d7-4773-be2e-ff64b566af6b)

## Características principales

1. 💯 Gratis y de código abierto.
2. ✨ Conversaciones con LLM de IA, multimodal, Agent, MCP, habilidades, base de conocimiento, configuración de personalidad, compresión automática de contexto.
3. 🤖 Soporta integración con Dify, Alibaba Cloud Bailian, Coze y otras plataformas de Agent.
4. 🌐 Multiplataforma: QQ, WeChat Work, Feishu, DingTalk, cuentas oficiales de WeChat, Telegram, Slack y [más](#plataformas-de-mensajería-soportadas).
5. 📦 Extensiones mediante plugins con más de 1000 plugins disponibles para instalación en un clic.
6. 🛡️ [Agent Sandbox](https://docs.astrbot.app/use/astrbot-agent-sandbox.html) para ejecución aislada y segura de código, llamadas a shell y reutilización de recursos a nivel de sesión.
7. 💻 Soporte de WebUI.
8. 🌈 Soporte de Web ChatUI con Agent Sandbox integrado y búsqueda web.
9. 🌐 Soporte de internacionalización (i18n).

<br>

<table align="center">
  <tr align="center">
    <th>💙 Juego de roles y compañía emocional</th>
    <th>✨ Agent proactivo</th>
    <th>🚀 Capacidades Agentic generales</th>
    <th>🧩 Más de 1000 plugins de la comunidad</th>
  </tr>
  <tr>
    <td align="center"><p align="center"><img width="984" height="1746" alt="99b587c5d35eea09d84f33e6cf6cfd4f" src="https://github.com/user-attachments/assets/89196061-3290-458d-b51f-afa178049f84" /></p></td>
    <td align="center"><p align="center"><img width="976" height="1612" alt="c449acd838c41d0915cc08a3824025b1" src="https://github.com/user-attachments/assets/f75368b4-e022-41dc-a9e0-131c3e73e32e" /></p></td>
    <td align="center"><p align="center"><img width="974" height="1732" alt="image" src="https://github.com/user-attachments/assets/e22a3968-87d7-4708-a7cd-e7f198c7c32e" /></p></td>
    <td align="center"><p align="center"><img width="976" height="1734" alt="image" src="https://github.com/user-attachments/assets/0952b395-6b4a-432a-8a50-c294b7f89750" /></p></td>
  </tr>
</table>

## Inicio rápido

### Despliegue en un clic

Para los usuarios que quieran experimentar AstrBot rápidamente, estén familiarizados con el uso de la línea de comandos y puedan instalar un entorno `uv` por su cuenta, recomendamos el método de despliegue en un clic con `uv` ⚡️:

```bash
uv tool install astrbot --python 3.14
astrbot init # Ejecuta este comando solo la primera vez para inicializar el entorno
astrbot run
```

> Requiere tener [uv](https://docs.astral.sh/uv/) instalado.
> AstrBot requiere Python 3.14 o superior. La opción `--python 3.14` asegura que `uv` cree el entorno de la herramienta con Python 3.14.

> [!NOTE]
> Para usuarios de macOS: debido a las comprobaciones de seguridad de macOS, la primera ejecución del comando `astrbot` puede tardar más (aproximadamente 10-20s).

Actualizar `astrbot`:

```bash
uv tool upgrade astrbot --python 3.14
```

> [!WARNING]
> AstrBot desplegado mediante `uv` **no soporta la actualización a través de la WebUI**. Para actualizar, ejecuta el comando anterior desde la línea de comandos.

### Despliegue con Docker

Para usuarios familiarizados con contenedores y que buscan un método de despliegue más estable y listo para producción, recomendamos desplegar AstrBot con Docker / Docker Compose.

Consulta la documentación oficial: [Desplegar AstrBot con Docker](https://docs.astrbot.app/deploy/astrbot/docker.html#%E4%BD%BF%E7%94%A8-docker-%E9%83%A8%E7%BD%B2-astrbot).

### Desplegar en RainYun

Para usuarios que desean un despliegue en un clic y no quieren administrar servidores por sí mismos, recomendamos el servicio de despliegue en la nube en un clic de RainYun ☁️:

[![Desplegar en RainYun](https://rainyun-apps.cn-nb1.rains3.com/materials/deploy-on-rainyun-en.svg)](https://app.rainyun.com/apps/rca/store/5994?ref=NjU1ODg0)

### Despliegue como aplicación de escritorio

Para usuarios que quieran usar AstrBot en el escritorio y principalmente usen ChatUI, recomendamos AstrBot App.

Visita [AstrBot-desktop](https://github.com/AstrBotDevs/AstrBot-desktop) para descargar e instalar; este método está diseñado para uso en escritorio y no se recomienda para escenarios de servidor.

### Despliegue con Launcher

Para usuarios de escritorio que también desean un despliegue rápido y uso aislado de múltiples instancias, recomendamos AstrBot Launcher.

Visita [AstrBot Launcher](https://github.com/AstrBotDevs/astrbot-launcher) para descargar e instalar.

### AUR

El despliegue mediante AUR está dirigido a usuarios de Arch Linux que prefieren instalar AstrBot a través del flujo de trabajo de paquetes del sistema.

Ejecuta el siguiente comando para instalar `astrbot-git`, luego inicia AstrBot en tu entorno local.

```bash
yay -S astrbot-git
```

**Más métodos de despliegue**

Si necesitas gestión basada en panel o una personalización más profunda, consulta [Despliegue con BT-Panel](https://docs.astrbot.app/deploy/astrbot/btpanel.html) para la configuración desde la tienda de aplicaciones de BT Panel, [Despliegue con 1Panel](https://docs.astrbot.app/deploy/astrbot/1panel.html) para el despliegue desde el mercado de aplicaciones de 1Panel, [Despliegue con CasaOS](https://docs.astrbot.app/deploy/astrbot/casaos.html) para despliegue visual en NAS/servidor doméstico, y [Despliegue manual](https://docs.astrbot.app/deploy/astrbot/cli.html) para una instalación completamente personalizada desde el código fuente con `uv`.

## Plataformas de mensajería soportadas

Conecta AstrBot a tu plataforma de chat favorita.

| Plataforma                                                                        | Mantenedor |
| --------------------------------------------------------------------------------- | ---------- |
| QQ                                                                                | Oficial    |
| Implementación del protocolo OneBot v11                                           | Oficial    |
| Telegram                                                                          | Oficial    |
| Wecom y Wecom AI Bot                                                              | Oficial    |
| Cuentas oficiales de WeChat                                                       | Oficial    |
| Feishu (Lark)                                                                     | Oficial    |
| DingTalk                                                                          | Oficial    |
| Slack                                                                             | Oficial    |
| Discord                                                                           | Oficial    |
| LINE                                                                              | Oficial    |
| Satori                                                                            | Oficial    |
| KOOK                                                                              | Oficial    |
| Misskey                                                                           | Oficial    |
| Mattermost                                                                        | Oficial    |
| WhatsApp (Próximamente)                                                           | Oficial    |
| [Matrix](https://github.com/stevessr/astrbot_plugin_matrix_adapter)               | Comunidad  |
| [Rocket.Chat](https://github.com/NET-Homeless/astrbot_plugin_rocket_chat_adapter) | Comunidad  |
| [VoceChat](https://github.com/HikariFroya/astrbot_plugin_vocechat)                | Comunidad  |

## Servicios de modelo soportados

| Servicio                                                                                           | Tipo                                                   |
| -------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| OpenAI y servicios compatibles                                                                     | Servicios LLM                                          |
| Anthropic                                                                                          | Servicios LLM                                          |
| Google Gemini                                                                                      | Servicios LLM                                          |
| Moonshot AI                                                                                        | Servicios LLM                                          |
| Zhipu AI                                                                                           | Servicios LLM                                          |
| DeepSeek                                                                                           | Servicios LLM                                          |
| Ollama (Autoalojado)                                                                               | Servicios LLM                                          |
| LM Studio (Autoalojado)                                                                            | Servicios LLM                                          |
| [AIHubMix](https://aihubmix.com/?aff=4bfH)                                                         | Servicios LLM (API Gateway, soporta todos los modelos) |
| [CompShare](https://www.compshare.cn/?ytag=GPU_YY-gh_astrbot&referral_code=FV7DcGowN4hB5UuXKgpE74) | Servicios LLM                                          |
| [302.AI](https://share.302.ai/rr1M3l)                                                              | Servicios LLM                                          |
| [TokenPony](https://www.tokenpony.cn/3YPyf)                                                        | Servicios LLM                                          |
| [SiliconFlow](https://docs.siliconflow.cn/cn/usercases/use-siliconcloud-in-astrbot)                | Servicios LLM                                          |
| [PPIO Cloud](https://ppio.com/user/register?invited_by=AIOONE)                                     | Servicios LLM                                          |
| ModelScope                                                                                         | Servicios LLM                                          |
| OneAPI                                                                                             | Servicios LLM                                          |
| Dify                                                                                               | Plataformas LLMOps                                     |
| Aplicaciones de Alibaba Cloud Bailian                                                              | Plataformas LLMOps                                     |
| Coze                                                                                               | Plataformas LLMOps                                     |
| OpenAI Whisper                                                                                     | Servicios de voz a texto                               |
| SenseVoice                                                                                         | Servicios de voz a texto                               |
| Xiaomi MiMo Omni                                                                                   | Servicios de voz a texto                               |
| OpenAI TTS                                                                                         | Servicios de texto a voz                               |
| Gemini TTS                                                                                         | Servicios de texto a voz                               |
| GPT-Sovits-Inference                                                                               | Servicios de texto a voz                               |
| GPT-Sovits                                                                                         | Servicios de texto a voz                               |
| FishAudio                                                                                          | Servicios de texto a voz                               |
| Edge TTS                                                                                           | Servicios de texto a voz                               |
| Alibaba Cloud Bailian TTS                                                                          | Servicios de texto a voz                               |
| Azure TTS                                                                                          | Servicios de texto a voz                               |
| Minimax TTS                                                                                        | Servicios de texto a voz                               |
| Xiaomi MiMo TTS                                                                                    | Servicios de texto a voz                               |
| Volcano Engine TTS                                                                                 | Servicios de texto a voz                               |

## ❤️ Patrocinadores

<p align="center">
  <img alt="sponsors" src="https://sponsors.astrbot.app/?v=1">
</p>

## ❤️ Contribuir

¡Issues y Pull Requests son siempre bienvenidos! No dudes en enviar tus cambios a este proyecto :)

### Cómo contribuir

Puedes contribuir revisando issues o ayudando con la revisión de pull requests. Cualquier issue o PR es bienvenido para fomentar la participación de la comunidad. Por supuesto, estas son solo sugerencias: puedes contribuir de la manera que prefieras. Para agregar nuevas funcionalidades, por favor discútelo primero a través de un Issue.

### Entorno de desarrollo

AstrBot usa `ruff` para el formateo y linting de código.

```bash
git clone https://github.com/BegoniaHe/AstrBot.git
pip install pre-commit
pre-commit install
```

## 🌍 Comunidad

### Grupos de QQ

- Grupo 1: 322154837 (Lleno)
- Grupo 3: 630166526 (Lleno)
- Grupo 4: 1077826412 (Lleno)
- Grupo 5: 822130018 (Lleno)
- Grupo 6: 753075035 (Lleno)
- Grupo 7: 743746109 (Lleno)
- Grupo 8: 1030353265 (Lleno)
- Grupo 9: 1076659624 (Lleno)
- Grupo 10: 1078079676 (Lleno)
- Grupo 11: 704659519 (Lleno)
- Grupo 12: 916228568 (Lleno)
- Grupo 13: 1092185289
- Grupo 14: 1103419483

- Grupo de desarrolladores (Charla): 975206796
- Grupo de desarrolladores (Formal): 1039761811

### Servidor de Discord

<a href="https://discord.gg/hAVk6tgV36"><img alt="Discord_community" src="https://img.shields.io/badge/Discord-AstrBot-purple?style=for-the-badge&color=76bad9"></a>

## ❤️ Agradecimientos especiales

Un agradecimiento especial a todos los contribuidores y desarrolladores de plugins por sus contribuciones a AstrBot ❤️

<a href="https://github.com/BegoniaHe/AstrBot/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=BegoniaHe/AstrBot&max=300&columns=15" />
</a>

Además, el nacimiento de este proyecto no habría sido posible sin la ayuda de los siguientes proyectos de código abierto:

- [NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ) - El increíble framework felino

## ⭐ Historial de estrellas

> [!TIP]
> Si este proyecto te ha ayudado en tu vida o trabajo, o si estás interesado en su desarrollo futuro, por favor dale una estrella al proyecto. Es la fuerza impulsora detrás del mantenimiento de este proyecto de código abierto <3

<div align="center">

[![Gráfico de historial de estrellas](https://api.star-history.com/svg?repos=astrbotdevs/astrbot&type=Date)](https://star-history.com/#astrbotdevs/astrbot&Date)

</div>

<div align="center">

_La compañía y la capacidad nunca deberían estar en conflicto. Lo que aspiramos a crear es un robot que pueda entender emociones, proporcionar compañía genuina y realizar tareas de manera confiable._

_私は、高性能ですから!_

<img src="https://files.astrbot.app/watashiwa-koseino-desukara.gif" width="100"/>
</div>
