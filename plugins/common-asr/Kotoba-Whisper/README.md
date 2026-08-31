# Kotoba-Whisper 通用 ASR 服务

基于 Hugging Face Transformers 和默认模型 `kotoba-tech/kotoba-whisper-v2.0`，实现父目录定义的 `GET /health` 与同步 `POST /job` 契约。该模型专用于日语识别，响应语言固定为 `ja`。

## 云服务器部署

要求：Linux、Python 3.10/3.11、NVIDIA GPU（推荐）、与驱动匹配的 CUDA PyTorch，以及系统命令 `ffmpeg`。模型只会在云服务器首次启动时从 Hugging Face 下载；本目录不包含模型权重。

```bash
cd plugins/common-asr/Kotoba-Whisper
python -m venv .venv
source .venv/bin/activate

# 先按云服务器 CUDA 版本安装 PyTorch，下面只是 CUDA 12.4 示例：
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt

uvicorn app:app --host 0.0.0.0 --port 8001 --workers 1
```

只能使用一个 Uvicorn worker，否则每个 worker 都会各自加载一份 GPU 模型。模型在后台加载，加载期间 `/health` 返回 `503`；就绪后返回 `200`。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ASR_MODEL_ID` | `kotoba-tech/kotoba-whisper-v2.0` | Hugging Face 模型 ID 或本地模型目录 |
| `ASR_DEVICE` | `auto` | `auto`、`cuda:0` 或 `cpu` |
| `ASR_API_KEY` | 空 | 非空时启用 Bearer Token |
| `ASR_MAX_UPLOAD_BYTES` | `1073741824` | 上传上限 |
| `ASR_FFMPEG_BIN` | `ffmpeg` | ffmpeg 命令或绝对路径 |
| `ASR_FFMPEG_TIMEOUT_SECONDS` | `1800` | 音频解码超时 |
| `KOTOBA_DTYPE` | `auto` | `auto`、`float32`、`float16` 或 `bfloat16` |
| `KOTOBA_ATTENTION` | GPU 为 `sdpa` | 可改为 `eager`；安装 Flash Attention 后可用 `flash_attention_2` |
| `KOTOBA_BATCH_SIZE` | `8` | Transformers 长音频批大小 |
| `KOTOBA_CHUNK_LENGTH_SECONDS` | `0` | `0` 使用精度更高的顺序长音频算法；设为 `15`/`25` 启用更快的分块算法 |
| `HF_HOME` | Hugging Face 默认值 | 云服务器模型缓存目录 |

## 测试

```bash
curl http://127.0.0.1:8001/health

curl -X POST http://127.0.0.1:8001/job \
  -F 'audio=@sample.wav' \
  -F 'language=ja'

curl -X POST http://127.0.0.1:8001/job \
  -F 'audio=@sample.wav' \
  -F 'language=ja' \
  -F 'segments=[{"index":0,"start_ms":1000,"end_ms":5000}]'
```

服务会先用 ffmpeg 将任意受支持输入统一转换为 16 kHz 单声道 PCM WAV。外部 `segments` 会按边界切片，返回块与输入一一对应；未传时使用 Transformers 返回的 segment timestamps。

默认使用官方说明中精度更高的 sequential long-form 模式。单个长音频追求速度时，可将 `KOTOBA_CHUNK_LENGTH_SECONDS=15` 或 `25`。
