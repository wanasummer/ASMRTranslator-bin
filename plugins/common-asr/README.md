# 通用 ASR 服务对接规范

本文定义 `asmrTranstor` 可直接接入的通用 ASR HTTP 契约。实现方至少必须提供：

- `GET /health`：健康检查与能力发现；
- `POST /job`：接收音频并同步返回完整 ASR 结果。

`POST /job` 返回的 JSON 就是 ASR 下一工作流的输入。调用方不应再解析供应商私有字段，也不应以 VTT 作为主数据源。

## 1. 通用约定

- 协议：HTTP/1.1 或 HTTP/2；生产环境建议使用 HTTPS。
- 编码：请求中的 JSON 和所有 JSON 响应均使用 UTF-8。
- 媒体类型：JSON 响应必须为 `application/json; charset=utf-8`。
- 时间单位：所有时间戳均为整数毫秒，并且基于上传的完整原始音频绝对时间轴。
- 字段命名：使用 `snake_case`。
- 契约版本：当前固定为整数 `1`。
- 未知字段：消费者应忽略未知字段，服务端不得改变本文已定义字段的类型或语义。
- 鉴权：允许不鉴权；需要鉴权时统一使用 `Authorization: Bearer <token>`。
- 请求追踪：建议支持 `X-Request-ID`。若调用方传入，服务端应在响应头中原样返回。

## 2. 健康检查

```http
GET /health
```

此接口不得触发模型推理。服务已启动且能够接收任务时返回 `200 OK`：

```json
{
  "status": "ok",
  "contract_version": 1,
  "service": "example-asr",
  "ready": true,
  "capabilities": {
    "languages": ["ja", "zh", "en"],
    "timestamps": true,
    "external_segments": true,
    "max_upload_bytes": 1073741824
  }
}
```

字段规则：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `status` | string | 是 | 健康时固定为 `ok`，不可用时为 `error` |
| `contract_version` | integer | 是 | 当前固定为 `1` |
| `service` | string | 是 | 稳定的服务实现标识 |
| `ready` | boolean | 是 | 模型和运行时是否已就绪 |
| `capabilities.languages` | string[] | 是 | 支持的 BCP 47 语言代码；至少使用 `ja`、`zh`、`en` 这类基础代码 |
| `capabilities.timestamps` | boolean | 是 | 是否能返回分块时间戳；兼容实现必须为 `true` |
| `capabilities.external_segments` | boolean | 是 | 是否支持调用方提供时间片段 |
| `capabilities.max_upload_bytes` | integer | 是 | 最大音频上传字节数 |

服务进程存活但模型未就绪时返回 `503 Service Unavailable`，响应仍使用统一错误格式：

```json
{
  "error": {
    "code": "SERVICE_NOT_READY",
    "message": "ASR model is not ready",
    "retryable": true,
    "details": {}
  }
}
```

## 3. 执行 ASR 任务

```http
POST /job
Content-Type: multipart/form-data
```

`/job` 是同步接口：服务端在 HTTP 响应中直接返回完整 ASR 结果。若一次推理可能超过网关超时，实现方应提高服务端和反向代理超时；不得先返回私有任务 ID 破坏本契约。调用方建议将请求超时设置为不低于 6 小时。

### 3.1 请求字段

| 字段 | multipart 类型 | 必填 | 说明 |
|---|---|---:|---|
| `audio` | file | 是 | 待识别的完整音频；建议支持 WAV、MP3、FLAC、M4A、OGG |
| `language` | text | 否 | BCP 47 源语言代码；省略或传 `auto` 表示自动检测 |
| `segments` | JSON string | 否 | 调用方指定的识别时间片段，格式见下文 |
| `request_id` | text | 否 | 调用方生成的幂等/追踪 ID，建议使用 UUID |

`segments` 示例：

```json
[
  {"index": 0, "start_ms": 1200, "end_ms": 4600},
  {"index": 1, "start_ms": 5100, "end_ms": 8300}
]
```

约束：

- `index` 必须是从 `0` 开始、连续递增的整数；
- `start_ms >= 0`，且 `end_ms > start_ms`；
- 片段必须按时间升序排列且不得重叠；相邻片段允许有空隙；
- `end_ms` 不得超过音频实际时长；
- 传入 `segments` 时，服务必须逐片识别并保留每个输入片段的边界和索引，即使某片段未识别出文本也必须返回对应空文本块；
- 未传 `segments` 时，由 ASR 服务自行切分，但返回结果仍须满足第 4 节的标准格式。

请求示例：

```bash
curl -X POST "http://127.0.0.1:8000/job" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "audio=@audio.wav" \
  -F "language=ja" \
  -F 'segments=[{"index":0,"start_ms":1200,"end_ms":4600},{"index":1,"start_ms":5100,"end_ms":8300}]'
```

### 3.2 成功响应

成功时返回 `200 OK`。以下对象可直接交给 ASR 后续的清洗、翻译和字幕工作流：

```json
{
  "contract_version": 1,
  "stage": "asr",
  "language": "ja",
  "source": "example-asr-model-v1",
  "timeline_source": "external_segments",
  "duration_ms": 120000,
  "text": "今日もお疲れさまでした。ゆっくり休んでください。",
  "blocks": [
    {
      "index": 0,
      "start_ms": 1200,
      "end_ms": 4600,
      "text": "今日もお疲れさまでした。",
      "skip_tts": false
    },
    {
      "index": 1,
      "start_ms": 5100,
      "end_ms": 8300,
      "text": "ゆっくり休んでください。",
      "skip_tts": false
    }
  ],
  "metadata": {
    "model": "example-asr-model-v1"
  }
}
```

## 4. 下游直连返回契约

### 4.1 顶层字段

| 字段 | 类型 | 必填 | 规则 |
|---|---|---:|---|
| `contract_version` | integer | 是 | 固定为 `1` |
| `stage` | string | 是 | 固定为 `asr`，下游用它校验阶段边界 |
| `language` | string | 是 | 实际识别文本的 BCP 47 语言代码；自动检测也不得返回 `auto` 或空字符串 |
| `source` | string | 是 | 实际 ASR 实现或模型的稳定标识，用于诊断 |
| `timeline_source` | string | 是 | 传入 `segments` 时为 `external_segments`，否则为 `asr` |
| `duration_ms` | integer | 是 | 完整上传音频时长，必须大于 `0` |
| `text` | string | 是 | 按 `blocks` 顺序拼接得到的完整转写文本；无语音时允许为空字符串 |
| `blocks` | object[] | 是 | 标准字幕块数组；无语音时允许为空数组 |
| `metadata` | object | 否 | 诊断信息；不得放置下游必需数据，也不得包含密钥或凭证 |

### 4.2 `blocks` 字段

每个块必须包含且只依赖以下稳定字段：

| 字段 | 类型 | 必填 | 规则 |
|---|---|---:|---|
| `index` | integer | 是 | 从 `0` 开始并按数组位置连续递增 |
| `start_ms` | integer | 是 | 完整原始音频绝对时间轴上的开始时间，包含端点 |
| `end_ms` | integer | 是 | 完整原始音频绝对时间轴上的结束时间，不包含端点，且大于 `start_ms` |
| `text` | string | 是 | 原始识别文本，必须保留 Unicode；无语音时为 `""`，不可为 `null` |
| `skip_tts` | boolean | 是 | ASR 阶段固定为 `false`；后续清洗流程负责决定是否跳过 TTS |

下游兼容性的强制规则：

1. `blocks` 必须按 `start_ms` 升序排列，时间范围不得重叠。
2. 时间戳必须是完整音频的绝对毫秒，不能是分片内相对时间，也不能使用秒或浮点数。
3. 不得把说话人标签拼进 `text`。若实现方能识别说话人，可额外返回可选的 `speaker` 字符串字段。
4. 不得在 ASR 阶段翻译文本；`language` 必须描述 `text` 的实际语言。翻译属于下一工作流。
5. 传入外部 `segments` 时，返回块必须与输入片段一一对应，禁止因空文本而丢块、合并块或改写边界。
6. 未传外部 `segments` 时，服务可自行分块；每个块仍必须有有效时间范围。
7. 空白文本应规整为 `""`；非空文本首尾不得保留无意义空白。
8. `text` 应与所有非空 `blocks[*].text` 按顺序连接后的内容语义一致。下游以 `blocks` 为权威时间轴。

## 5. 错误响应

所有非 `2xx` 响应必须使用同一错误包络：

```json
{
  "error": {
    "code": "INVALID_SEGMENTS",
    "message": "segments[1].end_ms exceeds audio duration",
    "retryable": false,
    "details": {
      "segment_index": 1,
      "duration_ms": 8000
    }
  }
}
```

建议状态码与错误码：

| HTTP | `error.code` | 使用场景 | `retryable` |
|---:|---|---|---:|
| `400` | `INVALID_REQUEST` | multipart 或字段格式错误 | false |
| `401` | `UNAUTHORIZED` | Token 缺失或无效 | false |
| `413` | `AUDIO_TOO_LARGE` | 音频超过上传限制 | false |
| `415` | `UNSUPPORTED_AUDIO` | 不支持或无法解码音频 | false |
| `422` | `INVALID_SEGMENTS` | 时间片段违反契约 | false |
| `429` | `RATE_LIMITED` | 并发或配额受限 | true |
| `500` | `ASR_FAILED` | 推理失败 | 视原因而定 |
| `503` | `SERVICE_NOT_READY` | 模型未就绪或服务过载 | true |
| `504` | `ASR_TIMEOUT` | 推理超时 | true |

错误响应不得以 `200 OK` 返回，也不得在失败时返回部分 `blocks` 冒充成功结果。

## 6. 最小兼容性验收

一个服务只有同时满足以下条件才算兼容：

- `/health` 就绪时返回 `200`、`ready: true` 和 `contract_version: 1`；
- `/job` 接受 multipart 音频并同步返回第 4 节定义的对象；
- 中文、日文等 Unicode 文本可无损返回；
- 所有时间戳均为原始音频绝对毫秒；
- 外部片段输入和返回块保持索引、边界及数量一一对应；
- 返回块有序、不重叠，且 `skip_tts` 为布尔值；
- 无语音音频成功返回空 `text` 与空 `blocks`，而不是伪造文本；
- 非法音频、非法时间片段和服务未就绪均返回规范错误包络。

## 7. 版本演进

- 向后兼容的新字段可直接增加；消费者必须忽略未知字段。
- 删除字段、修改类型、改变时间单位或字段语义属于破坏性变更，必须提升 `contract_version`。
- `contract_version: 1` 的 `stage`、`language`、`timeline_source` 和 `blocks` 语义必须保持不变。
