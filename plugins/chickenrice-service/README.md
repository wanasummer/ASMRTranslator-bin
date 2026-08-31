# ChickenRice Subtitle Service

可独立部署的模块化字幕后端。安装时一次性准备日语 ASR、海南鸡 ASMR VAD、日语直出中文模型和推理运行库；调用接口时再自由组合是否使用 VAD、使用哪条时间轴以及输出日文或中文。插件分发包不内置模型或 NVIDIA 二进制，安装器负责下载并验证，用户无需手动克隆海南鸡仓库或安装完整 CUDA Toolkit。

## 功能组合

| `vad_provider` | `output_language` | 行为 |
|---|---|---|
| `none` | `ja` | 核心日语 ASR，使用 ASR 片段时间戳 |
| `external` | `ja` | 使用调用方 VAD 时间轴生成日语块（主项目推荐） |
| `chickenrice` | `ja` | 海南鸡 ASMR VAD + 日语 ASR |
| `none` / `external` / `chickenrice` | `zh` | 使用可选中文模型直出中文字幕 |

`external` 模式把传入的每个 VAD 切片视为 authored timeline：输出原样保留 `index/start_ms/end_ms` 和顺序，即使某个切片识别为空也不会丢块。Whisper 片段时间戳不会覆盖该时间轴。

## 安装

要求 Python 3.10/3.11 x64。GPU 服务端只需预先安装可支持 CUDA 12 的 NVIDIA 驱动；Windows 安装器会自动安装 cuBLAS 12、cuDNN 9、CTranslate2 和全部模型，并真实加载一次 Whisper 模型完成验收：

```powershell
cd plugins/chickenrice-service
.\install.ps1 -Device cuda
.\start.ps1 -Device cuda -HostAddress 127.0.0.1 -Port 7870
```

`start.ps1` 每次启动前都会运行只读自检。缺少 DLL、驱动不可用或模型不完整时会立即退出，不会启动一个错误显示 `ready` 的服务。也可以单独运行：

```powershell
.\.venv\Scripts\python.exe -m chickenrice_service --runtime-dir runtime --device cuda --check
```

没有 NVIDIA GPU 时可安装 CPU 版（推理会明显更慢）：

```powershell
.\install.ps1 -Device cpu
.\start.ps1 -Device cpu -HostAddress 0.0.0.0 -Port 7870
```

Linux：

```bash
./install.sh cuda
./start.sh cuda
```

安装器优先验证环境变量代理，再探测 `7890/7897/10809/10808/20171/2080` 等本地端口。只有代理能实际访问 HTTPS 时才使用；否则自动切换 GitHub、Hugging Face 和 PyPI 国内镜像。

## Docker 部署

```bash
cp .env.example .env
# GPU 默认使用 CHICKENRICE_ENGINE_EXTRA=engine-gpu
docker compose up -d --build
curl http://127.0.0.1:7870/health
```

服务器 GPU 模式需要 NVIDIA 驱动和 NVIDIA Container Toolkit。模型保存在 Docker volume，更新容器不会重复下载。

## 健康检查

`GET /health` 同时检查模型、VAD 文件和实际推理运行时。GPU 不完整时返回 HTTP 200 但 `status=not_ready`，并在 `runtime.problems` 中列出缺失的 DLL 或驱动问题：

```json
{
  "status": "ready",
  "version": "0.3.0",
  "device": "cuda",
  "runtime": {
    "available": true,
    "provider": "ctranslate2-cuda",
    "problems": []
  }
}
```

## API

核心日语 ASR（不使用 VAD）：

```bash
curl -X POST http://127.0.0.1:7870/v1/jobs \
  -H "Authorization: Bearer YOUR_KEY" \
  -F "audio=@audio.wav" \
  -F "vad_provider=none" \
  -F "output_language=ja"
```

接收当前项目自己的 VAD 时间轴：

```bash
curl -X POST http://127.0.0.1:7870/v1/jobs \
  -F "audio=@audio.wav" \
  -F "vad_provider=external" \
  -F "output_language=ja" \
  -F 'segments=[{"index":0,"start_ms":1200,"end_ms":4600}]'
```

使用海南鸡 VAD 并直接生成中文：

```bash
curl -X POST http://127.0.0.1:7870/v1/jobs \
  -F "audio=@audio.wav" \
  -F "vad_provider=chickenrice" \
  -F "output_language=zh"
```

查询和获取结果：

```text
GET    /health
GET    /v1/jobs/{job_id}
GET    /v1/jobs/{job_id}/result
GET    /v1/jobs/{job_id}/subtitles.vtt
DELETE /v1/jobs/{job_id}
```

`result` 是主项目可直接消费的 ASR 阶段契约：

```json
{
  "contract_version": 1,
  "stage": "asr",
  "language": "ja",
  "source": "chickenrice-ja-asr",
  "vad_provider": "external",
  "timeline_source": "external_vad",
  "blocks": [
    {
      "index": 0,
      "start_ms": 1200,
      "end_ms": 4600,
      "text": "今日もお疲れさまでした。",
      "skip_tts": false
    }
  ]
}
```

日语输出应进入当前项目的日语清洗、总结和翻译阶段；中文直出可以跳过这些阶段，但仍应经过现有中文短句过滤规则后进入 TTS。服务不会把日语文本静默送入中文 TTS。

服务使用单工作线程保护单张 GPU，任务状态和结果持久化，默认保留 24 小时。可通过 `CHICKENRICE_API_KEY` 启用 Bearer Token 鉴权。

## 分发包

```powershell
.\package.ps1
```

输出位于 `dist/chickenrice-service-<version>.zip`，同时生成 SHA-256。ZIP 包含插件源码与安装脚本，不包含模型、NVIDIA 运行库、虚拟环境或用户任务；这些内容由服务器上的安装器按平台下载。

## 固定模型与许可证

- 日语 ASR：`TransWithAI/whisper-ja-1.5B-ct2`
- 可选中文模型：`chickenrice0721/whisper-large-v2-translate-zh-v0.2-st-ct2`（Apache-2.0）
- 可选 ASMR VAD：`TransWithAI/Whisper-Vad-EncDec-ASMR-onnx`（MIT）
- 可选上游运行时：`TransWithAI/Faster-Whisper-TransWithAI-ChickenRice` `v1.10`（MIT）

下载内容保留各自许可证。升级固定版本前应使用项目 ASMR 样本集回归时间轴、漏译和幻听。

## GPU 故障处理

新版不要求手工安装 CUDA Toolkit。若旧安装曾出现 `cublas64_12.dll is not found`，在服务器解压新版插件后执行：

```powershell
.\install.ps1 -Device cuda -Force
.\start.ps1 -Device cuda -HostAddress 0.0.0.0 -Port 7870
```

安装器会从 Python 包索引下载 NVIDIA 官方 Windows 运行库。可用 `CHICKENRICE_GPU_RUNTIME_DIR` 指向自备的 CUDA/cuDNN DLL 目录；通常无需设置。
