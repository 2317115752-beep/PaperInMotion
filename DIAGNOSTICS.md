# 运行与故障记录

## 2026-11-17 百炼迁移

项目当前接入阿里云百炼北京地域：`qwen3.8-flash` 负责论文理解与分镜，`qwen-audio-3.1-tts-flash` 负责中英文配音。需要在 `.env` 填写 `DASHSCOPE_API_KEY` 和 `BAILIAN_WORKSPACE_ID`。以下 Hugging Face / Together 故障记录保留作历史诊断，不代表当前调用链。真实百炼调用以本机验证结果为准。

2026-11-17（香港时间）。代码、数据与依赖都直接保存在本桌面项目。

## 已观察到的会话工具问题

- 截图仅显示空错误框，本身没有错误码，无法据此确定中断根因。
- 本轮联网检索工具返回 HTTP 404：`/codex/alpha/search` 接口不存在。
- 协作工具的子任务返回 `Agent errored:`，没有正文。
- 本机 Codex 日志中存在辅助标题生成 HTTP 400：配置的线路不支持 `gpt-6-luna`。该条只证明标题辅助请求失败，不能据此认定主对话失败原因。
- 因此有证据表明部分工具/辅助模型路由异常，但无法仅凭这些信息确认全部断连是否来自同一处中转服务。未修改用户的 Codex 或网络配置。

## 项目自己的渲染问题

此前 Remotion 报 root component 初始化超时。会话恢复后，同一构建的初始化与完整中文渲染已成功；没有证据证明某处代码修改解决了它。中文演示已输出1152帧、1280×720、24fps、48秒H.264视频，无音轨（预制静音演示）。

## 日志位置

- `data/server.log`：当前后端服务输出。
- `data/<任务ID>/job.json`：持久化任务状态。
- `data/<任务ID>/render.log`：渲染器事件与错误。
- `data/<任务ID>/error.log`：任务异常堆栈，HF_TOKEN会被替换。
- `data/qa/`：本地验证画面与合成测试音，不是模型生成结果。

真实付费 API 尚未测试，HF_TOKEN 当前为空；中文与英文演示不调用 API。

## 最终本地验证

- 中文和英文各一份48秒静音演示，720p / H.264 / 24fps。
- 合成测试音短片包含AAC音轨，解码后有非零音频样本。
- 13项单元测试和前端生产构建通过。
- MP4/SRT/JSON/ZIP下载成功；MP4分段请求返回206；ZIP完整。
- 刷新恢复上次任务；390px与1440px宽度无横向溢出。
- 一键启动脚本实测启动服务并保存日志。验证清单：`data/qa/verification.json`。

## 配音402的已确认原因（2026-11-17）

一次仅包含“你好。”的独立配音调用，由HF官方路由 `router.huggingface.co/together/v1/audio/speech` 返回HTTP402，服务端原文为：`Pay-as-you go is not enabled for provider together yet.` 这说明本次HF路由计费拒绝，不足以认定用户余额耗尽。不能因此要求用户再次充值HF或认定必须充值Together。未使用论文内容做该诊断。

已修正全部402显示“额度不足”的错误分类，保留脱敏服务说明/响应主机/请求ID，配音前保存分镜检查点。原先失败任务已存在于job.json的分镜也已另存storyboard-plan.json。修改通过22项离线测试。切换语音API/凭证仍需进一步接入，未验证成功配音。

另一个待核查项：真实模型调用统计仍出现reasoning_tokens，说明请求中的关闭思考参数没有确保HF路由实际关闭思考；先前离线检查只能证明请求构造，不能证明供应商生效。


## 百炼工作空间地址400（2026-11-17）

当前请求曾由业务空间专属域名返回 `HTTP 400 code=invalid_parameter_error: Workspace endpoint is invalid.`。同一 API Key 向官方北京通用地址 `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions` 发送极短 JSON 测试，已返回 HTTP 200 与预期内容。因此该错误指向专属域名的工作空间地址配置，不能归为论文长度、音色或余额问题。

默认配置已改用 `BAILIAN_ENDPOINT_MODE=shared`，通用模式只要求北京地域的 `DASHSCOPE_API_KEY`，并按密钥归属选择业务空间；不会使用已填写的 `BAILIAN_WORKSPACE_ID` 拼接地址。需要专属域名时，才显式选择 `workspace` 模式并填写对应 ID。页面与 README 已同步更新。上述真实检查只验证短文本接口，未据此宣称完整论文视频生成或配音调用已经成功。

### 北京接口与真实配音联调修复

原业务空间拼接地址返回 `Workspace endpoint is invalid`；同一密钥在官方通用北京接口的 `qwen3.8-flash` 最小文本请求返回 HTTP 200。默认改为 `BAILIAN_ENDPOINT_MODE=shared`，业务空间由 API Key 归属决定。专属模式应从控制台 API Host 复制正确前缀。

`qwen-audio-3.1-tts-flash` 真实中英文音频均已返回。服务的 PCM WAV 使用 RIFF/data 占位长度 `0x7fffffbf`/`0x7fffff9b`；程序对这一特定格式按下载完整字节数修正头部，再校验并测量时长。英文测试 2.16 秒，中文测试 2.64 秒。

## 引用核对失败修复（2026-11-18）

失败任务的 PDF 有 32 页可选正文，共 21,452 字符，未截断；355 处换行位于汉字之间。原空白折叠会把换行变成词内空格；实际模型诊断还出现省略号和改写引用。改为让模型选择当前文档的稳定证据片段编号，由程序回填原文和物理页码；旧格式只在确定性排版规范化后严格匹配，并可按真正匹配的页修复页码。未知编号、改写、数值或否定词变更仍被拒绝。核对前保留模型草稿及逐条诊断，避免把引用失败误报为扫描 PDF。43 项离线测试通过；完整实测记录待下方补充。
