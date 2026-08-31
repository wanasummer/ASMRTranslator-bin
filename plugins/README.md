# ASMRTranslator 插件资源

此目录保存 ASMRTranslator Studio v1.5.2 对外发布的插件源代码、部署脚本和接口规范。模型权重、虚拟环境、运行日志、测试缓存及开发期构建产物不纳入仓库。

## 外部 ASR 开发者

请以 [`common-asr/README.md`](common-asr/README.md) 作为唯一通用 ASR 接口契约。它定义了：

- `GET /health` 服务发现与就绪检查；
- `POST /job` 音频上传及同步识别；
- `contract_version: 1` 的请求/响应结构；
- 毫秒级绝对时间轴、标准分段字段与稳定标识；
- Bearer 鉴权、请求追踪、错误响应和兼容性规则。

`common-asr/Kotoba-Whisper` 与 `common-asr/Parakeet` 是可运行的参考实现，可用于验证第三方服务的路由、字段和错误处理。

## 官方插件资源

- [`chickenrice-service`](chickenrice-service/README.md)：日语 ASR 与字幕生成服务，支持 PowerShell、Shell 和 Docker 部署。
- [`Genie-TTS`](Genie-TTS/README.md)：本地 Genie TTS 服务，支持离线推理及音色导入；接口详情见 [`API.md`](Genie-TTS/API.md)。

各插件的依赖、模型下载和启动方法以其目录内 README 为准。
