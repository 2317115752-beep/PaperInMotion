# Paper in Motion

论文转教学视频 Agent 首版。上传 PDF，选择中文或英文，调用阿里云百炼 `qwen3.8-flash` 理解论文和编排分镜，调用 `qwen-audio-3.1-tts-flash` 生成所选语言的旁白，再用 Remotion 渲染 MP4。模型均通过 API 调用，不下载模型权重。

## 配置百炼

项目在本机桌面的 `PaperInMotion` 文件夹，实际配置文件是该目录下的 `.env`。已准备好模型配置，默认使用北京通用接口，申请凭证后填写 API Key：

```dotenv
DASHSCOPE_API_KEY=填写北京地域的API_Key
BAILIAN_ENDPOINT_MODE=shared
```

在[阿里云百炼控制台](https://bailian.console.aliyun.com/cn-beijing/model/market)选择北京地域，在密钥管理中创建 API Key。API Key 与调用地址需属于同一地域。通用接口通过 API Key 识别所属业务空间，无需额外填写业务空间 ID；已有的 `BAILIAN_WORKSPACE_ID` 在 `shared` 模式下不会用于拼接地址。密钥创建步骤见[官方指南](https://help.aliyun.com/zh/model-studio/get-api-key)，空间归属见[业务空间说明](https://help.aliyun.com/zh/model-studio/use-workspace)。密钥只填入本机 `.env`，不需要发到聊天或粘贴到前端。

其余配置已有默认值：

```dotenv
BAILIAN_CHAT_MODEL=qwen3.8-flash
BAILIAN_CHAT_MAX_TOKENS=12000
BAILIAN_TTS_MODEL=qwen-audio-3.1-tts-flash
BAILIAN_TTS_VOICE_ZH=loongbella_v3.1
BAILIAN_TTS_VOICE_EN=loongbella_v3.1
```

中英文分别生成对应语言的讲稿和配音；`loongbella_v3.1` 支持这两种语言。默认使用官方仍支持的北京通用域名：

- 论文理解与分镜：`https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`
- 语音合成：`https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer`

若明确需要业务空间专属域名，可在 `.env` 设置 `BAILIAN_ENDPOINT_MODE=workspace`，从官方控制台「业务空间管理 → API Host」复制专属域名的完整前缀（例如 `llm-xxx`）作为 `BAILIAN_WORKSPACE_ID`，不要仅凭数字空间 ID 推测域名。该模式使用 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com`，必须确认 ID 对应可用的专属接口；`Workspace endpoint is invalid` 表示此地址不被服务接受。通用模式不依赖这个 ID。官方[地域接入说明](https://help.aliyun.com/zh/model-studio/regions)推荐专属 API Host；目前所选文本和配音模型已在本机通用接口实测可用。

保存 `.env` 后，在页面右上角「模型配置」点击「重新读取配置」。页面只显示填写状态，实际可用性需要调用验证。可先在项目目录检查配置：

```bash
.venv/bin/python scripts/check_bailian.py
```

填写完成后，运行以下命令会实际调用一次短文本规划和中英文短配音，按百炼规则计费：

```bash
.venv/bin/python scripts/check_bailian.py --live
```

真实生成会把论文正文、最多 4 张页面图片和配音文字发送到阿里云百炼。API 按量收费，失败前已完成的调用也可能计费。项目已切换到百炼，不再使用 Hugging Face Token 或余额。

## 安装与启动

本机已安装依赖，可直接双击 `Start.command`。启动器会打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)，并保存日志；再次启动会复用已有服务。

在新机器安装需要 Node.js 22.12+、Python 3.11+（推荐 3.12）与 uv：

```bash
uv venv --python 3.12
uv pip install -r requirements-lock.txt
npm ci
npm run build
cp .env.example .env
# 编辑 .env，填写北京地域的 DASHSCOPE_API_KEY
python3 scripts/start.py
```

已有 `.env` 时直接编辑，请勿用示例文件覆盖。首次渲染可能下载 Remotion Chromium 浏览器。

未配置 API 时仍可使用内置 LoRA 演示：预制分镜、Python 执行的玩具矩阵、实际渲染的 48 秒静音视频。演示明确标注无 API、无配音，可用于检查界面与视频形式。

## 输出与首版范围

- 真实生成完成后，在视频预览右下方点击「下载视频」导出 MP4；任务卡片中可下载 SRT 字幕、分镜 JSON 和含音轨及渲染器的可编辑项目 ZIP。
- 输出同时保存在 `data/<任务ID>/`，API 密钥不包含在导出的项目中。
- PDF 正文提取与最多 4 张页面图片，最大 25 MB、80 页、100,000 正文字符；扫描 PDF 暂不支持。
- 模型从带编号的原文片段中选择依据，程序从当前 PDF 回填引用与物理页码，拒绝不存在的编号。兼容旧逐字引用时仅规范排版差异并严格匹配，不接受改写或翻译。此检查只确认引用可定位，不等于主张与证据的语义一致性审核。
- 白名单计算器支持低秩矩阵更新与缩放点积注意力，其他方法使用定性流程图；不会执行模型生成的任意代码。
- 结构化分镜由固定 Remotion 动画模板渲染为 720p 视频，按 API 音频的实测时长安排场景。
- 字幕在音频段内按句长估计时间，尚未接入逐字强制对齐。最终视频时长可能偏离目标。
- 一次处理一个任务，状态保存在 `data/`，页面刷新会恢复上次任务；服务重启时运行中任务标为中断。
- 仅绑定本机地址，无账号隔离；发布为多人服务需要另加认证、配额与独立存储。

## 开发与排查

后端：`.venv/bin/python -m uvicorn backend.app:app --port 8000`。前端：`npm run dev`（5173 端口代理 API）。

离线测试：`.venv/bin/python -m unittest discover -s tests -v`。前端检查：`npm run build`。无 API 音轨验证：`.venv/bin/python scripts/verify_audio_render.py`，使用合成测试音检查渲染。

服务日志在 `data/server.log`；每个任务的渲染日志在 `data/<任务ID>/render.log`，异常详情在同目录 `error.log`。引用问题可查看 `method-draft.json`（核对前模型结果）、`evidence-excerpts.json`（原文片段表）和 `evidence-check.json`（逐条核对结果）。模型调用日志保留脱敏的服务端错误码、说明和请求 ID，可区分密钥、地域、权限、额度或参数错误。历史 Hugging Face 路由问题见 `DIAGNOSTICS.md`。

分镜与论文理解默认最多 12,000 个输出 token，可用 `BAILIAN_CHAT_MAX_TOKENS` 调整。上限不是目标长度；实际调用按百炼规则计费。原始 HTTP 请求通过顶层 `enable_thinking: false` 关闭思考模式，并请求 JSON 对象。1 / 2 / 3 分钟视频分别提示生成 4 / 6 / 8 幕，并限制整段讲稿长度。

`finish_reason=length` 始终作为未完成处理，即使截断文本碰巧是有效 JSON。程序不会因此自动追加一次收费重试。各任务的 `model_calls.jsonl` 只保存阶段、输出上限、结束原因、token 计数与文本长度，不保存密钥、响应正文或思考内容。论文理解通过引用检查后保存 `method.json`；配音前保存 `storyboard-plan.json`。重新提交会创建新任务，暂不自动续跑旧分析。

官方参考：[文本 API](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)、[语音 HTTP API](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-http-api)、[音色列表](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-voice-list)、[模型价格](https://help.aliyun.com/zh/model-studio/model-pricing)。

实际配音兼容：百炼可能返回带流式占位长度的标准 PCM WAV。本项目仅对已观察并验证的特定占位头修正文件长度，再按实际采样帧计算时长；普通截断、损坏音频仍停止生成。
