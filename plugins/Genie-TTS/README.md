# Genie TTS Plugin

这是 [Genie-TTS](https://github.com/High-Logic/Genie-TTS) 的独立本地引擎插件，安装位置固定为 `plugins/Genie-TTS/`。它拥有自己的 manifest、API 契约、隔离虚拟环境、运行资源和角色配置，不依赖其他 TTS 插件。主程序不需要安装或导入 Genie、ONNX Runtime 和各语言 G2P 依赖，只通过插件自己的 HTTP API 调用。

## 设计边界

- 插件只负责将一个中文片段合成为语音。
- 输出固定为 24 kHz、单声道、16-bit PCM WAV。
- Genie 内部使用进程级共享上下文，因此所有推理强制串行，`recommended_concurrency=1`。
- 插件不修改字幕时间线，也不做最终时长补齐；响度匹配、变速、截断、DSP 和拼接仍由主项目处理。
- 插件包不包含 GenieData、角色模型、参考音频、虚拟环境或用户配置。
- Genie 代码为 MIT；角色声音、模型和参考音频必须由用户提供或确认拥有使用权。

## 安装

需要 Windows x64 和 Python 3.10/3.11 x64：

```powershell
cd plugins/Genie-TTS
.\install.ps1 -DownloadBaseResources
```

不希望安装阶段下载约 391 MB GenieData 时，可以省略 `-DownloadBaseResources`，由未来的插件安装器根据 manifest 的 `resources` 字段下载。插件不再附带或自动下载角色音色；用户需要在 GPT-SoVITS 中训练 V2/V2ProPlus 音色、用 Genie 转换为 ONNX，然后从主程序的 Genie 配置界面临时选择。

安装脚本会创建插件自己的 `.venv` 和 `runtime/voices.json`，不会修改主项目的 `pyproject.toml` 或 Python sidecar。

网络线路固定按以下顺序尝试：

1. Python 包优先使用清华 TUNA PyPI 镜像，模型优先使用 `hf-mirror.com`；
2. 国内镜像失败后，若 `127.0.0.1:7890` 可连接，则通过该代理访问官方源；
3. 最后只尝试一次官方直连并给出明确错误。模型下载并发限制为 2，避免安装阶段占用过多内存和网络连接。

服务不会根据可用内存预先阻止模型加载。只有 Genie 或 ONNX Runtime 在实际加载、生成时返回内存分配失败，接口才会提示运行时内存不足。

## 为本次生成选择用户音色

在主程序中选择“Genie 本地插件”→“选择模型目录”，选择与 `CharacterModels/v2ProPlus/feibi` 同结构的角色根目录：

```text
my_voice/
├─ tts_models/       # .onnx 计算图和 .bin/.data 外部权重
├─ prompt_wav/       # 参考音频
└─ prompt_wav.json   # wav 文件名和准确文本
```

目录名会直接作为本次生成使用的音色名称。插件优先使用 `prompt_wav.json` 的 `Normal` 记录，只校验并直接读取原目录，不复制模型、不记录模型存放位置；重复选择同名目录会覆盖当前临时选择。结构错误会在前端明确提示，插件服务重启后需重新选择。

模型说话人和输出语言是两个不同概念：当前 ASMRTranslator 插件接口输出中文，因此 `language` 应设为 `zh`；如果参考音频本身是日语，可以把 `reference_language` 设为 `jp`，并填写准确日文转录。

## 启动与检查

```powershell
.\start.ps1
curl.exe http://127.0.0.1:8003/health
curl.exe http://127.0.0.1:8003/voices
```

带本地鉴权启动：

```powershell
.\start.ps1 -ApiKey "your-local-token"
```

调用合成：

```powershell
$body = @{
  contract_version = 1
  request_id = "demo-1"
  segment_index = 0
  text = "欢迎回来，今天也辛苦了。"
  speaker = "遥"
  voice_id = "asmr-girl"
  language = "zh-CN"
  rate = "+0%"
  pitch = "+0Hz"
  output = @{
    container = "wav"; codec = "pcm_s16le"
    sample_rate_hz = 24000; channels = 1
  }
} | ConvertTo-Json -Depth 4
Invoke-WebRequest -Uri http://127.0.0.1:8003/job -Method Post `
  -ContentType "application/json" -Body $body -OutFile demo.wav
```

Genie 2.0.2 不提供原生 `rate`/`pitch` 控制，因此插件只接受 `+0%` 和 `+0Hz`。主项目原有的时长预算阶段仍会按字幕窗口进行保音高变速或截断。

## 分发

```powershell
.\package.ps1
```

输出 `dist/genie-tts-service-<version>.zip` 和 SHA-256 文件。未来插件安装器可以读取 `plugin-manifest.json`，创建隔离环境、下载 `resources`、生成 `runtime/voices.json`，然后使用 manifest 中的启动入口。
