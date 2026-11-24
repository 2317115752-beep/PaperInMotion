# Paper in Motion

论文转教学视频工作台。上传论文及可选的补充 PDF，选择中文或英文旁白。`qwen3.8-flash` 负责论文理解和分镜，`qwen-audio-3.1-tts-flash` 负责旁白，Remotion 负责渲染。界面默认英文，可在右上角切换为中文。界面语言和旁白语言分别设置。

## 使用工作台

按下方的 Windows 或 macOS 说明启动项目，再打开 [视频工作台](http://127.0.0.1:8000)。上传 PDF 后选择目标时长、讲解深度和 Editorial、Midnight 或 Classroom 主题。内置 LoRA 和 CLIFF 演示可用于预览计算动画，演示没有云配音。

工作台会显示任务进度和旧任务。成片可下载 MP4、SRT、分镜、音轨、可编辑 Remotion ZIP 和评估 JSON。对已完成的视频，可以按论文理解、示例、分镜或制作阶段创建修改版。更换主题和编辑单幕旁白会复用仍可用的已合成音频。失败任务可从已保存的分镜或分析阶段继续。

### 画面风格

画面风格控制成片的背景、文字、图形高亮和字幕配色。只更换风格时，可以通过已完成任务的制作修订复用原分镜和音轨。

| 选项 | 成片效果 | 适合场景 |
| --- | --- | --- |
| 研究简报（Editorial，默认） | 暖米白背景、深色正文和绿色高亮，字幕为深底浅字，整体接近研究简报。 | 论文概览、组会汇报。 |
| 深色演示（Midnight） | 深蓝背景搭配浅色文字和亮蓝高亮，字幕为浅底深字，公式和当前步骤在暗色画面中更突出。 | 偏好深色画面或在较暗环境中观看。 |
| 课堂讲解（Classroom） | 浅蓝背景搭配白色卡片、深蓝文字和蓝色高亮，字幕为深蓝底浅字。 | 课堂播放、课程讲解。 |

### 目标受众

目标受众影响模型编排讲稿和分镜时强调的内容。同一语言、同一目标时长下，两档使用相同的分镜数量和讲稿长度预算，实际片长随配音而定。具体讲解内容会随论文和生成结果变化。

| 选项 | 讲解重点 | 以 LoRA 为例 |
| --- | --- | --- |
| 入门（Introductory，默认） | 面向有基础机器学习知识的观众，按操作讲清输入、处理步骤和输出。 | 先说明为什么冻结原权重，再用小矩阵分别演算原路径和低秩更新，最后合并结果。 |
| 进阶（Advanced） | 面向熟悉机器学习基础的观众，强调步骤间的依赖、方法的假设和设计取舍。 | 进一步说明秩如何影响可训练参数量和更新的表达能力，以及何时可以将更新合并进原权重。 |

## 配置百炼

在你下载或克隆的 `PaperInMotion` 项目根目录编辑 `.env`。默认使用北京通用接口，申请凭证后填写 API Key：

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

保存 `.env` 后，在工作台右上角打开模型设置并重新读取配置。也可在项目目录运行配置检查脚本：

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe scripts/check_bailian.py
```

```bash
# macOS
.venv/bin/python scripts/check_bailian.py
```

在对应平台的命令末尾加上 `--live`，可以验证一次短文本规划和中英文短配音。这会产生百炼 API 用量。

生成时会把论文文字、选取的页面图片和旁白文本发送到阿里云百炼。API 按量收费，失败前已完成的调用也可能计费。

## 安装与启动

两种系统均需要 Git、Node.js 22.12 或更新版本（包含 npm），以及 uv。以下命令由 uv 准备 Python 3.12 和项目虚拟环境。安装工具后，新开一个终端再执行命令。[Git](https://git-scm.com/downloads) · [Node.js](https://nodejs.org/en/download) · [uv](https://docs.astral.sh/uv/getting-started/installation/)

### Windows（PowerShell）

```powershell
git clone https://github.com/2317115752-beep/PaperInMotion.git
Set-Location PaperInMotion
uv venv --python 3.12
uv pip install --python .\.venv\Scripts\python.exe -r requirements-lock.txt
npm.cmd ci
npm.cmd run build
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad.exe .env
```

在记事本按上方说明填写 `DASHSCOPE_API_KEY` 并保存。若先体验内置演示，可以将密钥留空。回到同一个 PowerShell 窗口启动：

```powershell
.\.venv\Scripts\python.exe scripts/start.py
```

直接调用虚拟环境的 Python 和 `npm.cmd` 即可，无需激活虚拟环境或调整 PowerShell 执行策略。

### macOS（终端）

```bash
git clone https://github.com/2317115752-beep/PaperInMotion.git
cd PaperInMotion
uv venv --python 3.12
uv pip install --python .venv/bin/python -r requirements-lock.txt
npm ci
npm run build
[ -f .env ] || cp .env.example .env
open -e .env
```

在文本编辑中按上方说明填写 `DASHSCOPE_API_KEY` 并保存。若先体验内置演示，可以将密钥留空。回到同一个终端启动：

```bash
.venv/bin/python scripts/start.py
```

以后启动时可以直接运行对应平台的启动命令。macOS 也可以在系统能找到 `python3` 时双击项目中的 `Start.command`。

### 打开与停止

启动器会打开浏览器。若未自动打开，请手动访问 [http://127.0.0.1:8000](http://127.0.0.1:8000)。按 `Ctrl+C` 停止服务。首次渲染可能需要联网下载 Remotion 使用的 Chromium，启动和任务日志位于 `data/`。

## Proposal 验收

| 要求 | 当前实现 |
| --- | --- |
| 论文与补充材料 | 用 PyMuPDF 读取正文、带位置的公式线索及可识别的图表。支持三份补充 PDF，引用标明文档和物理页。每份 25 MB、80 页，总计 50 MB。纯扫描件需要先 OCR，复杂图表的提取依赖 PDF 排版。 |
| 方法和执行 | 方法记录保留操作、输入、输出、中间状态、依赖和来源。LoRA、CLIFF、ResNet、NeRF、Adam、FlashAttention 等受支持的比较使用 Python 和 NumPy 实算，其他方法可生成示意讲解。引用定位和科学主张的语义审核分别记录。 |
| 动画和制作 | 模型输出结构化分镜，由程序绑定到 React、Remotion 和 SVG 组件，编译预览后渲染 1080p H.264/AAC。动画使用原论文图表和可执行示例的状态。公式支持常用符号与上下标。 |
| 配音和字幕 | 百炼流式返回 PCM。用各段实际采样数排定字幕、动画节拍和停顿，SRT 与画内字幕共用时间轴。片段内的动作位置仍为估计，目标片长以实际配音为准。 |
| 修订和评估 | 机械检查可验证媒体流、时长、字幕时间轴与计算检查点。研究工具结合模型或人工评分给出分阶段修订建议，可比较前后版本。 |
| A/B/C 和观看实验 | 提供四篇留出论文的 24 次生成计划、分派、评分、用量记录及结果汇总。正式批量生成、18–24 位参与者的观看实验与数据采集仍待执行。 |
| 跨论文适配 | 提供开发集的审核修订导出和留出集隔离。实际 LoRA 训练、适配模型部署和对照评估仍待执行。 |

为沿用现有百炼 API，论文解析采用 PyMuPDF，语音采用现有百炼模型，字幕采用实测片段长度。动画使用可编辑的组件和数据，支持在导出目录内运行 `npm ci` 和 `node rerender.mjs` 重新渲染。研究工具和待办步骤见 [研究操作手册](research/README.md)。

## 开发与排查

下表中的 Python 命令在 macOS 使用 `.venv/bin/python`，在 Windows PowerShell 使用 `.\.venv\Scripts\python.exe`。Windows PowerShell 可用 `npm.cmd` 执行对应 npm 命令。

| 用途 | 命令 |
| --- | --- |
| 单独启动后端 | `python -m uvicorn backend.app:app --port 8000` |
| 启动前端开发服务（5173 端口代理后端） | `npm run dev` |
| 离线测试 | `python -m unittest discover -s tests -v` |
| 前端构建 | `npm run build` |
| 用合成测试音检查渲染 | `python scripts/verify_audio_render.py` |

服务日志在 `data/server.log`；每个任务的渲染日志在 `data/<任务ID>/render.log`，异常详情在同目录 `error.log`。引用问题可查看 `method-draft.json`（核对前模型结果）、`evidence-excerpts.json`（原文片段表）和 `evidence-check.json`（逐条核对结果）。模型调用日志保留脱敏的服务端错误码、说明和请求 ID，可区分密钥、地域、权限、额度或参数错误。历史 Hugging Face 路由问题见 `DIAGNOSTICS.md`。

分镜与论文理解默认最多 12,000 个输出 token，可用 `BAILIAN_CHAT_MAX_TOKENS` 调整。上限不是目标长度；实际调用按百炼规则计费。原始 HTTP 请求通过顶层 `enable_thinking: false` 关闭思考模式，并请求 JSON 对象。1 / 2 / 3 分钟视频分别提示生成 4 / 6 / 8 幕，并限制整段讲稿长度。

`finish_reason=length` 作为未完成处理。`model_calls.jsonl` 保存阶段、输出上限、结束原因、用量和长度。`method.json`、`storyboard-plan.json` 和已完成的配音片段可用于重试。既有任务文件和新输出均保存在 `data/<任务ID>/`。

官方参考：[文本 API](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)、[语音 HTTP API](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-http-api)、[音色列表](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-voice-list)、[模型价格](https://help.aliyun.com/zh/model-studio/model-pricing)。

实际配音兼容：百炼可能返回带流式占位长度的标准 PCM WAV。本项目仅对已观察并验证的特定占位头修正文件长度，再按实际采样帧计算时长；普通截断、损坏音频仍停止生成。
