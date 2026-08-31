# ASMRTranslator Studio

面向日文 ASMR 的中文配音桌面工具。导入原始音频与可选字幕后，软件会完成音频切分、识别/翻译、中文配音、听感处理与结果导出。

桌面端采用 **Tauri 2 + Svelte 5**，后端使用 Python/Nuitka 编译，并提供可扩展的 TTS、ASR 与字幕服务插件。

---

## 下载最新版

| 版本 | 安装包 | 大小 | 发布日期 | 下载 |
| --- | --- | --- | --- | --- |
| **v1.5.2 测试版** | `ASMRTranslator Studio_1.5.2_x64-setup.exe` | 约 120.13 MB | 2026-08-31 | [下载安装包](ASMRTranslator%20Studio_1.5.2_x64-setup.exe) |

SHA-256：

```text
F5668E85E065C41CB1D44E53D18BB0D48CBF2F8BD78A505586CB224644C10A64
```

> 当前安装包尚未进行代码签名。Windows SmartScreen 可能显示“未知发布者”，请核对文件名和 SHA-256 后再运行。

---

## v1.5.2 最近更新

- **一个项目处理多个音频**：每段音频会在项目目录下使用音频文件名建立独立产物目录，字幕、配音、日志和最终音频不再互相混放。
- **任务记录按音频区分**：同一项目的不同音频可同时出现在等待队列与历史记录中；项目和文件名都相同时，新任务会覆盖旧记录。
- **修复重复日志**：修正异步事件订阅竞争导致同一条流水线日志被重复显示的问题。
- **扩展通用 ASR**：新增外部 ASR 服务配置及统一 HTTP 契约，并提供 Kotoba-Whisper、NVIDIA Parakeet 两套参考实现。
- **新增 ChickenRice 字幕插件**：支持日语 ASR、外部 VAD 时间轴、WebVTT 输出和可选日译中流程，可使用本地安装或 Docker 部署。
- **新增 Genie TTS 插件**：支持本地离线推理、GPT-SoVITS 音色克隆和自定义音色导入。
- **日语文本清洗可插拔**：新增基于 MeCab 的 ASR 日语清洗阶段，改善识别文本进入翻译前的质量。
- **桌面体验改进**：加入界面缩放，增强任务队列和音色库管理，并完成后端原生编译与 Rust 发布配置优化。

---

## 主要功能

- **项目化工作流**：创建或打开项目，分别管理多段音频、字幕、配音配置和每段音频的输出结果。
- **任务中心**：查看阶段、总进度、实时日志和最终输出，支持取消任务以及同项目多音频排队。
- **六套 TTS 引擎**：Edge TTS、MiMo TTS、Fish Audio、MiniMax、IndexTTS 2.5 与 Genie TTS。
- **音色工作台**：浏览和管理音色；支持服务商音色设计、参考音频克隆及本地音色导入。
- **可扩展 ASR**：支持 Fish ASR、通用 ASR HTTP 服务和 ChickenRice 字幕服务。
- **无字幕处理**：使用本地 FSMN-VAD 检测语音区间，再进行识别、翻译和字幕优化。
- **音频流程增强**：改进任务资源管理、重叠片段处理、LLM 响应解析和 TTS 伪影检测。

---

## 基本使用流程

1. 安装并启动 ASMRTranslator Studio。
2. 新建或打开项目，选择一段原始 ASMR 音频。
3. 按需选择 VTT、SRT 或 LRC 字幕；不提供字幕时可启用无字幕识别流程。
4. 选择 TTS 引擎、音色、听感模式和声音参数。
5. 启动转换，在任务中心查看进度与日志；可继续为同一项目添加其他音频任务。
6. 完成后从结果页打开导出的 MP3、WAV、字幕和日志文件。

每段音频的产物保存在项目目录下以音频文件名命名的子目录中。配置会自动保存到用户目录下的 `.asmrts` 文件。

---

## TTS 引擎

| 引擎 | 主要能力 | 凭证或服务 |
| --- | --- | --- |
| **Edge TTS** | 免费在线音色、语速与音高设置 | 无需 API Key，需要联网 |
| **MiMo TTS** | 标准音色、文字音色设计、参考音频克隆 | 需要 MiMo API Key |
| **Fish Audio** | 免费/高质量模型、音色库、音色设计与克隆 | 需要 Fish Audio API Key |
| **MiniMax** | 高质量与快速模型、系统及自定义音色 | 需要 MiniMax API Key |
| **IndexTTS 2.5** | 自托管参考音频克隆、情感权重 | 需要自行准备本地或云端服务 |
| **Genie TTS** | 本地离线推理、GPT-SoVITS 音色克隆 | 通过仓库内插件安装模型与服务 |

在线接口的可用模型、额度和计费以各服务商规则为准。

---

## 字幕与无字幕模式

- 支持 VTT、SRT、LRC 字幕文件。
- 有字幕时可直接按时间轴切分并配音，也可启用文字大模型优化字幕。
- 无字幕时可使用 FSMN-VAD 配合 Fish ASR、通用 ASR 服务或 ChickenRice 完成识别。
- 通用 ASR 可配置服务地址、端口和可选 Bearer API Key。
- 如需把 ASR 原文翻译成中文，需要配置 OpenAI 兼容接口或 Anthropic 接口。

---

## 插件与二次开发

本仓库的 [`plugins`](plugins/) 目录提供运行/部署所需文件及开放接口文档，不包含模型权重：

- [`CommonASR 通用 ASR 服务对接规范`](plugins/common-asr/README.md)：面向外部开发者的稳定 HTTP 契约，定义 `/health`、`/job`、时间戳、分段结果、鉴权、错误响应和兼容性要求。
- [`Kotoba-Whisper 参考实现`](plugins/common-asr/Kotoba-Whisper/README.md)：通用 ASR 契约的日语 Whisper 服务示例。
- [`Parakeet 参考实现`](plugins/common-asr/Parakeet/README.md)：基于 NVIDIA NeMo/Parakeet 的通用 ASR 服务示例。
- [`ChickenRice Subtitle Service`](plugins/chickenrice-service/README.md)：日语 ASR/字幕服务，包含安装脚本、Docker 配置和预构建插件压缩包。
- [`Genie TTS Service`](plugins/Genie-TTS/README.md)：本地 Genie TTS 服务；详细接口见 [`API.md`](plugins/Genie-TTS/API.md)。

第三方通用 ASR 服务只要遵守 CommonASR 契约，即可在不修改 ASMRTranslator 主流程的情况下接入。开发者应首先完成协议文档末尾的兼容性检查清单。

---

## 听感模式

- **仅替换**：用中文配音替换对应的原声片段。
- **保留原声**：保留原声并插入中文翻译音频。
- **同步叠加**：中文配音与原声同步播放，可选择跟随原声或跟随翻译。
- **潜意识同传**：在同步叠加基础上加入延迟、混响、齿音柔化、原声/尾声淡化等处理。

还可调整语速、翻译音量、交叉淡化、最大加速倍率，并启用 TTS 伪影检测。

---

## 系统要求

- Windows 10 / 11，64 位。
- Microsoft Edge WebView2 Runtime。多数 Windows 10/11 设备已预装。
- 使用在线 TTS、ASR、文字大模型或云端 IndexTTS 时需要联网。
- 本地 IndexTTS、Genie TTS、ChickenRice 或通用 ASR 服务需要按对应插件文档准备运行环境和模型。
- 请预留足够空间保存原始音频、项目文件、插件模型及 MP3/WAV 输出。

---

## 常见问题

### 没有字幕可以使用吗？

可以。可选择 Fish ASR、兼容 CommonASR 契约的服务或 ChickenRice；如需自动翻译成中文，还要配置文字大模型接口并开启自动翻译。

### 输出文件在哪里？

转换成功后可在结果页直接打开 MP3、WAV、字幕和日志。每段音频的全部产物都位于项目目录下同名的音频子目录中。

### 同一项目能处理多个音频吗？

可以。不同文件名会保留各自的任务记录和产物目录；重复提交同项目、同文件名的音频时，以新任务覆盖旧记录。

### IndexTTS 应该怎样连接？

填写服务地址和端口，默认端口为 `7860`。服务可以运行在当前电脑、局域网设备或云端 GPU 主机上，并需要选择一段清晰的单人参考音频。

### 为什么 Windows 提示未知发布者？

当前测试版尚未签名。请从本仓库下载，并核对上方 SHA-256。后续获得代码签名证书后会改善这一提示。

---

## 版本历史

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| **v1.5.2** | 2026-08-31 | 项目多音频与独立产物目录；修复重复日志；新增 Genie TTS、CommonASR、Kotoba-Whisper、Parakeet 与 ChickenRice；加入日语清洗、界面缩放和任务队列增强 |
| **v1.5.1** | 2026-08-25 | 修复了一些严重 Bug |
| **v1.5.0** | 2026-08-25 | 首个 Tauri 2 + Svelte 5 桌面版本：项目、任务与音色工作台，全新 UI，Nuitka 后端，ASR/LLM/音频流程增强 |
| v1.4.6 | 2026-08-22 | Electron 版：新增 IndexTTS 2.5 本地与云端服务接口 |
| v1.4.5 | 2026-08-16 | Electron 版：新增 MiniMax TTS、无字幕 ASR 模式与潜意识同传增强 |

---

## 交流群

<img width="300" alt="qrcode_1785593346923" src="https://github.com/user-attachments/assets/42cc5079-6537-46cc-9ab6-79f95c236955" />

*感谢使用 ASMRTranslator。祝你拥有舒适的中文 ASMR 体验。*

如需反馈问题或建议，请在本仓库 [Issues](../../issues) 中提出。
