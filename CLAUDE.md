# VoiceScribe WebUI

音视频转写 Web 应用 — 上传本地媒体文件或粘贴公开 URL。支持两种转写模式：faster-whisper ASR（高精度）和 YouTube 字幕直接抓取（快速、无需 GPU）。pyannote.audio 做 speaker diarization。前端 React 界面查看/编辑/翻译/导出结果，支持播客笔记生成、频道订阅管理和策展日报。

## 技术栈

- **前端**: React 18 + TypeScript + Vite 6 + Tailwind CSS 3 + React Router 6 + TanStack React Query 5 + Axios
- **后端**: FastAPI (Python) + SQLAlchemy 2 + Pydantic v2 + Celery + Redis
- **模型**: faster-whisper (ASR) + YouTube 字幕直取 (快速模式) + pyannote.audio (diarization) + Helsinki-NLP/opus-mt (本地翻译) + OpenAI-compatible / Anthropic API (LLM 翻译/纠错/分段/播客笔记/策展日报)
- **部署**: Docker Compose (redis + backend + worker + frontend 四服务)

## 目录结构

```
voicescribe-webui/
├── frontend/
│   └── src/
│       ├── App.tsx              # 路由 + 全局布局
│       ├── main.tsx             # React 入口
│       ├── api/                 # Axios 客户端 + API 调用
│       │   ├── client.ts        # axios 实例 (baseURL, 错误处理)
│       │   ├── jobs.ts          # 任务 CRUD + 上传/URL导入/导出/重试
│       │   ├── podcast.ts       # 播客笔记 + 推荐 + 订阅管理 + 策展日报 API
│       │   └── settings.ts      # 设置读写 API
│       ├── components/          # 可复用组件
│       │   ├── UploadBox.tsx        # 本地文件上传
│       │   ├── UrlImportBox.tsx     # URL 导入 (含转录模式选择: HF/YouTube字幕)
│       │   ├── TranscriptEditor.tsx # 转写片段编辑
│       │   ├── ParagraphViewer.tsx  # 语段版查看
│       │   ├── ExportButtons.tsx    # 导出按钮
│       │   ├── JobStatusBadge.tsx   # 任务状态标签
│       │   ├── SettingsDialog.tsx   # 设置弹窗
│       │   ├── PodcastNotesPanel.tsx        # 播客笔记面板
│       │   ├── PodcastRecommendationsPanel.tsx # 推荐面板 (含订阅列表搜索)
│       │   └── SubscriptionSourcesPanel.tsx    # 频道订阅源管理
│       ├── pages/
│       │   ├── HomePage.tsx      # 首页 — 上传/URL导入
│       │   ├── JobsPage.tsx      # 任务列表
│       │   ├── JobDetailPage.tsx # 任务详情 — 转写结果/编辑/导出/翻译/播客笔记
│       │   └── PodcastPage.tsx   # 播客笔记生成页
│       └── types/               # TypeScript 类型定义
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 应用入口, CORS, 路由注册
│   │   ├── config.py            # pydantic-settings 配置, 所有环境变量
│   │   ├── database.py          # SQLAlchemy 引擎/session/表创建/迁移
│   │   ├── models.py            # ORM 模型: Job (含 transcription_mode, progress_percent), TranscriptSegment, Paragraph, PodcastNote
│   │   ├── schemas.py           # Pydantic schemas (含订阅/策展日报/转录模式)
│   │   ├── api/                 # 路由层
│   │   │   ├── jobs.py          # /api/jobs — 核心 CRUD + upload/from-url/retry/segments/paragraphs
│   │   │   ├── export.py        # /api/jobs/{id}/export — TXT/SRT/VTT/JSON/MD 导出
│   │   │   ├── podcast.py       # /api/podcast — 播客笔记 + 推荐 + 订阅源管理 + 策展日报
│   │   │   └── settings.py      # /api/settings — 前端设置读写
│   │   ├── services/            # 业务逻辑层
│   │   │   ├── asr.py              # faster-whisper 转写
│   │   │   ├── youtube_transcript.py  # YouTube 字幕直取 + LLM 修复 (快速转录模式)
│   │   │   ├── diarization.py      # pyannote.audio speaker diarization
│   │   │   ├── alignment.py        # diarization 与 ASR segments 对齐
│   │   │   ├── media.py            # ffmpeg 音频提取/标准化
│   │   │   ├── downloader.py       # yt-dlp URL 下载
│   │   │   ├── translator.py       # 翻译 (本地 HF pipeline / OpenAI API)
│   │   │   ├── transcript_correction.py # 转写纠错 (rules/llm/off)
│   │   │   ├── paragraphing.py     # 语段分割 (rules/llm)
│   │   │   ├── exporter.py         # 导出格式生成
│   │   │   ├── podcast_notes.py    # 播客笔记生成 (调用 LLM)
│   │   │   └── podcast_recommendations.py # 相似内容推荐 + 订阅列表搜索 + 策展日报
│   │   ├── data/                # 本地数据文件
│   │   │   └── subscriptions.csv    # 订阅频道列表 (162 个 YouTube 频道, CSV 格式)
│   │   ├── workers/             # Celery 异步任务
│   │   │   ├── celery_app.py    # Celery app 定义
│   │   │   └── tasks.py         # 任务编排: process_job 主流程 (支持 HF/YouTube 双模式)
│   │   └── utils/
│   │       ├── logging.py       # 日志配置
│   │       └── time_format.py   # 时间格式化
│   └── requirements.txt
├── scripts/                     # macOS 启动/停止脚本
├── docker-compose.yml
└── .env                         # 环境变量 (不提交)
```

## 开发命令

```bash
# 后端
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload          # API: http://localhost:8000

# Celery worker (需要 Redis)
redis-server
celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --pool=solo

# 前端
cd frontend
npm install
npm run dev                            # http://localhost:5173

# 一键启动 (macOS)
scripts/start-voicescribe.sh

# Docker 部署
docker compose up --build
```

## 关键架构约定

### 后端
- **配置**: 所有配置通过 `get_settings()` 单例获取，环境变量前缀见 `config.py`。`.env` 在项目根目录。新增 `PODCAST_SUBSCRIPTION_CSV` 环境变量指定订阅 CSV 路径。
- **数据库**: SQLite 本地开发 (`storage/voicescribe.sqlite3`)，Docker 中用 volume 挂载。迁移通过 `_migrate_sqlite()` 手动 ALTER TABLE。Job 模型新增 `transcription_mode` 和 `progress_percent` 字段。
- **异步任务**: 默认走 Celery + Redis。设置 `RUN_TASKS_INLINE=true` 可绕过 Celery 用 FastAPI BackgroundTasks 兜底。
- **任务状态机**: `queued → downloading → extracting_audio → transcribing → correcting → diarizing → aligning → translating → segmenting → completed | failed`
- **转录双模式**:
  - `hf` (默认): 走传统 faster-whisper ASR 流程（下载音频 → ffmpeg → 转写 → 纠错 → diarization）
  - `youtube_transcript`: 直接从 YouTube 抓取字幕/自动字幕，再 LLM 修复分段，跳过音频下载和 ASR。仅适用于 URL 来源的 YouTube 链接，无需 GPU，速度快数十倍
  - 新建任务时通过 `transcription_mode` 参数选择
- **YouTube 字幕处理** (`youtube_transcript.py`): 先用 yt-dlp 获取元数据，按语言偏好选择字幕轨道（支持 json3 和 vtt 格式），再将原始字幕块合并分段后用 LLM 修复标点、大小写、错词和 speaker 标注
- **订阅频道管理** (`podcast_recommendations.py`): CSV 文件持久化 YouTube 频道列表，CRUD API (`GET/POST/DELETE /api/podcast/subscriptions`)，支持按 TF-IDF 相似度从订阅列表中筛选相关频道，用 yt-dlp 拉取近期视频参与推荐
- **策展日报** (`generate_curation_report`): 将推荐结果交给 LLM 生成深潮 TechFlow 风格的 Markdown 策展日报（今日总览、内容清单、专题组合建议、编辑建议、今天只做一条）。LLM 不可用时自动回退到本地模板。API: `POST /api/podcast/curation-report`
- **模型下载**: faster-whisper 和 pyannote 模型首次运行自动下载，`large-v3` 较大。
- **API 约定**: RESTful，路由注册在 `app/main.py`，业务逻辑在 `app/services/`，路由在 `app/api/`。
- **进度追踪**: Job 模型新增 `progress_percent` 字段，转录阶段实时更新百分比，YouTube 模式跳过音频处理直接从 0→100。

### 前端
- **状态管理**: TanStack React Query 管理服务端状态，组件内 `useState` 管理 UI 状态。
- **路由**: React Router v6，四个页面：`/` (新任务), `/jobs` (任务列表), `/jobs/:jobId` (任务详情), `/podcast` (播客)。
- **API 调用**: `src/api/client.ts` 创建 axios 实例，`VITE_API_BASE_URL` 环境变量配置后端地址。podcast API 新增订阅管理、策展日报、推荐请求支持 `search_subscriptions` 参数。
- **样式**: Tailwind CSS utility-first，自定义样式在 `styles.css`。
- **新组件**: `SubscriptionSourcesPanel` — 播客页面的频道订阅源管理面板，支持添加/搜索/删除订阅频道。

### Docker
- 四服务架构：redis, backend (FastAPI), worker (Celery), frontend (nginx 静态服务)
- 前端构建时注入 `VITE_API_BASE_URL` 指向后端 API
- 存储卷 `voicescribe_storage` 挂载到 backend 和 worker

## 新增 API

- `GET /api/podcast/subscriptions` — 获取订阅频道列表
- `POST /api/podcast/subscriptions` — 添加订阅频道
- `DELETE /api/podcast/subscriptions/{channel_id}` — 删除订阅频道
- `POST /api/podcast/curation-report` — 生成策展日报 (LLM 或本地回退)
- `POST /api/jobs/from-url` 新增 `transcription_mode: "hf" | "youtube_transcript"` 字段
- `POST /api/podcast/recommendations` 新增 `search_subscriptions: bool` 字段

## 注意事项

- `HF_TOKEN` 不配置时 speaker diarization 自动跳过，不影响转写
- YouTube 转录模式 (`transcription_mode=youtube_transcript`) 无需 HF token、GPU 或模型下载，适合快速处理 YouTube 内容
- yt-dlp 只处理公开内容，不传 cookie/登录凭据
- `.env`、`backend/storage/` 已在 `.gitignore`，不提交。`backend/app/data/subscriptions.csv` 可提交
- macOS `.app` 和 `.command` 启动脚本在 `scripts/` 目录
- 后端所有 LLM 调用 (纠错/翻译/分段/播客笔记/策展日报/YouTube字幕修复) 支持 Anthropic (`anthropic`) 和 OpenAI-compatible (`openai`) 双 provider，通过 `PARAGRAPHING_API_PROVIDER` 切换
