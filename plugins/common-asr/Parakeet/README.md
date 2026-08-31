# Parakeet 通用 ASR 服务

基于 NVIDIA NeMo 和默认模型 `nvidia/parakeet-tdt_ctc-0.6b-ja`，实现父目录定义的 `GET /health` 与同步 `POST /job` 契约。该模型专用于日语识别，响应语言固定为 `ja`。

## 模型说明

默认模型是 NVIDIA 官方的日语 Hybrid FastConformer TDT-CTC 0.6B，训练数据包含 ReazonSpeech。请求可省略 `language`、传 `auto`、`ja`、`ja-JP` 或 `japanese`；其他语言返回 `422 UNSUPPORTED_LANGUAGE`。

## 云服务器部署

要求：Linux、Python 3.10/3.11、NVIDIA GPU（推荐）、与驱动匹配的 CUDA PyTorch，以及系统命令 `ffmpeg`。模型只会在云服务器首次启动时从 Hugging Face 下载；本目录不包含模型权重。

```bash
cd plugins/common-asr/Parakeet
python -m venv .venv
source .venv/bin/activate

# 先按云服务器 CUDA 版本安装 PyTorch，下面只是 CUDA 12.4 示例：
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt

uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1
```

只能使用一个 Uvicorn worker，否则每个 worker 都会各自加载一份 GPU 模型。模型在后台加载，加载期间 `/health` 返回 `503`；就绪后返回 `200`。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ASR_MODEL_ID` | `nvidia/parakeet-tdt_ctc-0.6b-ja` | NeMo/Hugging Face 模型 ID |
| `ASR_DEVICE` | `auto` | `auto`、`cuda`、`cuda:0` 或 `cpu` |
| `ASR_API_KEY` | 空 | 非空时启用 Bearer Token |
| `ASR_MAX_UPLOAD_BYTES` | `1073741824` | 上传上限 |
| `ASR_FFMPEG_BIN` | `ffmpeg` | ffmpeg 命令或绝对路径 |
| `ASR_FFMPEG_TIMEOUT_SECONDS` | `1800` | 音频解码超时 |
| `PARAKEET_BATCH_SIZE` | `1` | 外部片段批量推理大小 |
| `PARAKEET_LOCAL_ATTENTION` | `true` | 对长音频启用局部注意力 |
| `PARAKEET_ATTENTION_CONTEXT` | `256` | 局部注意力左右上下文 |
| `HF_HOME` | Hugging Face 默认值 | 云服务器模型缓存目录 |

## 测试

```bash
curl http://127.0.0.1:8000/health

curl -X POST http://127.0.0.1:8000/job \
  -F 'audio=@sample.wav' \
  -F 'language=ja'

curl -X POST http://127.0.0.1:8000/job \
  -F 'audio=@sample.wav' \
  -F 'language=ja' \
  -F 'segments=[{"index":0,"start_ms":1000,"end_ms":5000}]'
```

服务会先用 ffmpeg 将任意受支持输入统一转换为 16 kHz 单声道 PCM WAV。外部 `segments` 会按边界切片，返回块与输入一一对应；未传时使用 NeMo 的原生 segment timestamps。
