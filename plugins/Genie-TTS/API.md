# Genie TTS Plugin API v1

本文件是 `plugins/Genie-TTS` 自有的进程间通信契约，不依赖其他插件规范。JSON 使用 UTF-8 和 `snake_case`。错误统一返回：

```json
{
  "error": {
    "code": "VOICE_NOT_FOUND",
    "message": "音色不存在: voice-a",
    "retryable": false,
    "details": {}
  }
}
```

## `GET /health`

返回插件、运行时和能力状态。模型、GenieData 或音色未就绪时返回 HTTP 503；就绪时返回 HTTP 200。`recommended_concurrency` 固定为 `1`，调用方不得并行请求该插件。

## `GET /voices`

返回当前服务已配置或为本次生成临时选择的音色。该接口不会加载 ONNX 模型，因此可以在低内存或尚未选择音色时用于配置界面：

```json
{
  "contract_version": 1,
  "stage": "tts_voice_catalog",
  "voices": [
    {
      "id": "voice-a",
      "name": "轻声女声",
      "gender": "female",
      "language": "zh-CN",
      "description": "自有中文模型"
    }
  ],
  "default_voice_id": "voice-a"
}
```

## `POST /voices/import`

临时选择用户在 GPT-SoVITS 中训练、再由 Genie `convert_to_onnx` 转换的完整角色目录。目录结构应与 `CharacterModels/v2ProPlus/feibi` 一致，路径必须是插件所在电脑可访问的本地绝对路径：

```json
{
  "character_dir": "D:\\Models\\my_voice"
}
```

角色目录必须包含 `tts_models/`、`prompt_wav/`、`prompt_wav.json`。插件以目录名作为音色名称，优先读取 `Normal` 参考记录并验证所有 ONNX 组件。服务直接读取用户选择的原目录，不复制、不持久化；同名音色可以重复选择，结构错误会返回 `INVALID_VOICE_BUNDLE`。

## `POST /job`

一次请求只合成一个字幕片段：

```json
{
  "contract_version": 1,
  "request_id": "demo-1",
  "segment_index": 0,
  "text": "欢迎回来。",
  "speaker": "遥",
  "voice_id": "voice-a",
  "language": "zh-CN",
  "rate": "+0%",
  "pitch": "+0Hz",
  "output": {
    "container": "wav",
    "codec": "pcm_s16le",
    "sample_rate_hz": 24000,
    "channels": 1
  }
}
```

成功返回完整 WAV 二进制，格式固定为 24 kHz、单声道、16-bit PCM。响应头包括：

- `X-Genie-TTS-API-Version: 1`
- `X-TTS-Segment-Index`
- `X-TTS-Voice-ID`
- `X-Audio-Duration-Ms`
- `X-Audio-Sample-Rate-Hz: 24000`
- `X-Audio-Channels: 1`
- `X-Audio-Codec: pcm_s16le`
- 请求包含 `request_id` 时原样返回 `X-Request-ID`

Genie 2.0.2 没有原生语速和音高控制，因此 v1 只接受 `rate="+0%"` 和 `pitch="+0Hz"`。时间轴适配、保音高变速、响度匹配和最终拼接属于主项目职责。
