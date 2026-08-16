# EchoScene

EchoScene turns YouTube AI videos into grounded real-time speaking practice. The version-one product is a Chrome Manifest V3 extension with a YouTube Side Panel, an application API, and a cloud-hosted LiveKit Agent boundary.

The current repository is a connected development build. It prepares exercises from real YouTube
captions, can use DeepSeek for grounded semantic content, and contains the real LiveKit browser,
token, and Agent boundaries. Live voice remains credential-gated and is never simulated when those
credentials are absent.

## 快速开始（交给你的编程 Agent）

EchoScene 是「自带 API Key」的开源模型：没有官方服务器，所有能力都在你自己的电脑上跑。
你只需要准备好 3 个 key，然后把下面这段话原样发给你的编程 Agent（Claude Code、Codex、
Cursor 等），它会帮你克隆、安装、构建插件并启动常驻服务。

> 把这整段发给你的 Agent：

```text
请帮我在本机安装并启动 EchoScene（一个把 YouTube 视频变成实时口语练习的 Chrome 插件）。

1. 克隆仓库 https://github.com/zhangzhangjingjing0408-coder/echoscene.git 到本地，进入项目目录。
2. 运行 ./scripts/install.sh（脚本会自动安装 uv 和 pnpm、创建隔离的 Python 3.12 虚拟环境、
   安装后端依赖、构建 Chrome 插件，并在 macOS 上注册两个常驻服务）。
3. 装完后确认 .env 已从 .env.example 生成（脚本会自动做，别覆盖我已有的 .env）。
4. 用 curl http://127.0.0.1:8787/health 确认 API 已启动，返回 status: ok 即成功。
5. 提示我打开项目根目录的 .env 填入三个 key（SUPADATA_API_KEY、DEEPSEEK_API_KEY、
   LIVEKIT_URL/LIVEKIT_API_KEY/LIVEKIT_API_SECRET，详见 README「三个需要你填的 key」）。
   我填完后，你再次运行 ./scripts/install.sh 让新配置生效。

只负责安装和启动，不要改动任何功能代码。
```

### 三个需要你填的 key

安装脚本不会替你填任何 key。装完后打开项目根目录的 `.env`，填入下表里的值：

| 能力 | 去哪里拿 | 填到 `.env` 的哪个字段 | 不填会怎样 |
| --- | --- | --- | --- |
| 字幕兜底 | [supadata.ai](https://supadata.ai) 注册，Dashboard 复制 API Key | `SUPADATA_API_KEY` | 仍可用 YouTube 自带字幕；偶发反爬失败时无兜底 |
| 深度练习内容 | [platform.deepseek.com](https://platform.deepseek.com) 注册充值，API Keys 新建 | `DEEPSEEK_API_KEY` | 降级为抽取式时间线（无语义总结/知识单元/任务） |
| 语音教练 | [cloud.livekit.io](https://cloud.livekit.io) 新建免费项目，Settings → Keys | `LIVEKIT_URL`、`LIVEKIT_API_KEY`、`LIVEKIT_API_SECRET` | 无法开启语音对话练习 |

LiveKit 免费套餐包含每月 1000 分钟 Agent 会话，语音教练走 LiveKit 内置推理
（Deepgram 转写 + Gemini 对话 + Cartesia 语音合成），不需要再单独申请这些语音 key。

> 不填 LiveKit 三件套也没关系：此时语音教练 Worker 会启动失败并反复重试（日志里持续出现
> `LIVEKIT_URL` 报错），这是预期行为，不影响字幕和深度练习。填好三件套后 Worker 会自动恢复，
> 无需手动干预。

> 成本提示：深度练习每次会调用 DeepSeek 生成结构化内容。`deepseek-v4-pro` 能力更强但较贵；
> 想省成本可把 `.env` 里的 `ECHOSCENE_CONTENT_MODEL` 改成 `deepseek-v4-flash`（价格约为 pro 的
> 1/3，日常口语练习足够）。

### 装好之后

1. 打开 `chrome://extensions`，开启右上角 **开发者模式**。
2. 点 **加载已解压的扩展程序**，选择 `apps/extension/dist`。
3. 打开任意一个 YouTube 视频页，刷新一次，点击视频标题旁的 **Practice with EchoScene**。
4. 首次使用会先准备字幕和深度内容，准备好后即可开始口语练习。

### 如何更新

功能有更新时（修复 bug 或加新功能），拉取最新代码并重新构建即可，**不会覆盖你已填好的 `.env`**：

```bash
git pull && ./scripts/install.sh
```

之后在 `chrome://extensions` 点一下「重新加载」让插件生效；后端服务（API 和语音教练）会由脚本自动重启，无需手动操作。

## What works in the skeleton

- Chrome Side Panel that follows the current YouTube light or dark theme
- `Practice with EchoScene` button injected into standard YouTube watch pages
- Current video title, channel, video ID, URL, playback position, and theme detection
- Timestamp action that seeks the YouTube player
- Anonymous installation ID stored locally in Chrome
- Real transcript preparation with open-source YouTube captions and Supadata fallback
- Evidence-grounded task prompt, source excerpt, and clickable timestamp
- DeepSeek full-transcript semantic overview, argument structure, 3–5 grounded knowledge units,
  reference-answer-driven vocabulary, and a multi-task path
- Progressive transcript-first preparation with validated server and Chrome caches, request
  coalescing, and phase-level latency/cache diagnostics
- Full scrollable timestamp transcript during preparation, guidance-language explanations, and
  chronological evidence anchors for semantically selected knowledge units
- Auditable extractive content fallback when no semantic-provider key is configured
- Complete Chinese or English guidance UI and localized task instruction
- FastAPI health, content preparation, LiveKit token, anonymous session, and trace endpoints
- LiveKit microphone publishing, Agent dispatch, remote audio playback, and explicit setup errors
- Two-attempt voice coach Worker constrained by the training state controller
- Deterministic training-state controller with legal-transition enforcement
- Provider boundaries for open-source YouTube transcripts and Supadata
- Versioned TypeScript contracts for tasks, transcript evidence, states, and trace events
- Trace redaction before persistence
- Unit, contract, API, state-machine, and packaging checks

## Repository map

```text
apps/
  extension/          Chrome extension and Side Panel
  api/                FastAPI application boundary
  agent/              training controller and LiveKit worker boundary
packages/
  contracts/          TypeScript schemas shared with the extension
  python/             shared Python utilities such as trace redaction
docs/
  product-decisions.md
AGENTS.md              repository-wide engineering instructions
.impeccable.md         persistent design context
```

## 开发者参考

> 以下内容是给 EchoScene 的开发者/贡献者本地开发用的。**新用户请使用上面的「快速开始」**，
> `./scripts/install.sh` 已经自动完成了下面的安装、构建和启动。不要手动运行
> `pip install -e '.[dev]'` —— 该命令不会安装语音教练所需的 LiveKit 依赖，会导致语音对话练习不可用。

### Prerequisites

- Node.js 22+
- pnpm 11+
- Python 3.11+
- Google Chrome 116+

### Install

```bash
pnpm install
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install --no-build-isolation -e '.[dev]'
```

Real LiveKit providers are optional and intentionally not installed by the base setup:

```bash
.venv/bin/python -m pip install --no-build-isolation -e '.[agent]'
```

Copy `.env.example` to `.env` only when you are ready to configure services. Never place real keys in source files, screenshots, chat messages, or traces.

### Build and install the extension

```bash
pnpm build
```

Then:

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Choose **Load unpacked**.
4. Select `apps/extension/dist`.
5. Open a standard `https://www.youtube.com/watch?...` page.
6. Refresh that YouTube tab once after initially loading the extension.
7. Click **Practice with EchoScene** beside the YouTube actions, or pin and click the extension icon.

The distributable ZIP is created with:

```bash
pnpm package:extension
```

Output: `apps/extension/echoscene-extension-<version>.zip`.

### Run the Side Panel as a web preview

```bash
pnpm dev:extension
```

Open `http://127.0.0.1:5173/sidepanel.html` for the light preview or append `?theme=dark` for the dark preview. The web preview uses explicit fallback video metadata because Chrome extension APIs are unavailable outside the extension.

### Run the API

```bash
.venv/bin/python -m uvicorn echoscene_api.main:app --reload --host 127.0.0.1 --port 8787
```

- OpenAPI: `http://127.0.0.1:8787/docs`
- Health: `http://127.0.0.1:8787/health`

Start the API before clicking **Prepare from this video**. By default it tries
`youtube-transcript-api`; add `SUPADATA_API_KEY` to enable the accepted fallback. The endpoint
returns an explicit error when captions are unavailable and never substitutes an unrelated task.

For semantic content preparation, add `DEEPSEEK_API_KEY` to `.env`. With the default
`ECHOSCENE_CONTENT_PROVIDER=auto`, the API uses `deepseek-v4-pro` when the key exists and the
auditable extractive fallback otherwise. To require DeepSeek and fail when it is not configured,
set `ECHOSCENE_CONTENT_PROVIDER=deepseek-semantic`.

If you keep settings in `.env`, start with:

```bash
.venv/bin/python -m uvicorn echoscene_api.main:app --reload --env-file .env --host 127.0.0.1 --port 8787
```

### Agent boundary

The first LiveKit Worker uses provisional harness candidates through LiveKit Inference:
Deepgram Nova-3 multilingual, Gemini 2.5 Flash Lite, and Cartesia Sonic 3.5. They remain replaceable
configuration and are not a final benchmark decision.

Set `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET`. EchoScene now uses a stable default
`ECHOSCENE_TTS_VOICE`; override it only when deliberately testing another voice. Then run:

```bash
.venv/bin/python -m echoscene_agent.worker dev
```

The API and Worker load the repository's ignored `.env.local` and `.env` automatically. The least
error-prone local setup is to authenticate the LiveKit CLI with `lk cloud auth`, select the project,
then run `lk app env -w` from this repository. Do not paste credentials into chat, extension
settings, screenshots, command history, or source files.

When changing Agent code, restart the Worker before browser validation; an already-running Worker
does not pick up the new coach-caption observer. Version 0.9 publishes coach captions from the
Agent's source text and keeps the current session record only in Side Panel memory. Persistent
practice history, scoring, and improvement guidance are intentionally deferred.

The API signs a 15-minute participant token and dispatches the named `echoscene` Agent. The Chrome
bundle receives only that temporary token; service credentials never enter extension source.
The Agent sends versioned realtime events for learner/coach transcripts, listening/thinking/speaking
state, controller-approved coaching actions, and detected interruptions. The Side Panel validates
these events before rendering them. The LLM must call one constrained action after each learner
turn; the deterministic controller rejects completion before the required targeted retry.

The first progressive stage is transcript study rather than a model-free warm-up question. The full
timestamped transcript is immediately searchable and exportable as TXT/SRT; supported YouTube
caption tracks can be translated to Chinese on demand without blocking semantic analysis. The API
owns the long semantic job, while the extension tracks it per video and guidance language and
presents a user-controlled entry when the formal practice path is ready.

Run the deterministic replay:

```bash
.venv/bin/python -m echoscene_agent.harness
```

The expected path includes preparation, briefing, prompting, listening, assessment, targeted retry, feedback, and completion. Illegal transitions fail closed.

### Quality checks

```bash
pnpm check
pnpm package:extension
```

`pnpm check` runs Python linting, TypeScript type checking, JavaScript and Python tests, and
production builds. Follow [Beta findings](docs/beta-findings.md) for the three-video grounding,
localization, and credentialed LiveKit retest gates.

The content and voice quality gates are documented in
[Harness Engineering](docs/harness-engineering.md). DeepSeek output must pass the same evidence,
schema, semantic, and human-review Harness; configuration alone does not establish quality.

### Confirmed boundaries

See [product decisions](docs/product-decisions.md) for version-one targets, transcript fallback policy, data retention, provider candidates, and deferred decisions. See [AGENTS.md](AGENTS.md) for rules all coding agents must follow.
