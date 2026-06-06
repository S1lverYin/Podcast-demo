# VoiceScribe WebUI

VoiceScribe WebUI 是一个用于音视频、播客和公开网页媒体转写的 Web 应用。它使用 FastAPI + Celery 处理后台任务，React + Vite 提供可视化界面，MVP 支持上传音频文件、调用 faster-whisper 转写、查看和编辑结果、导出 TXT/JSON，并预留 URL 解析、speaker diarization、SRT/VTT/Markdown 导出能力。

## 功能

- 上传本地视频：mp4, mov, mkv, webm
- 上传本地音频：mp3, wav, m4a, flac, aac
- 输入公开 URL：YouTube、播客 RSS、普通网页嵌入媒体；Bilibili、小宇宙、Apple Podcasts、Spotify podcast 页面已保留适配入口
- ffmpeg 自动提取并标准化音频为 16 kHz mono wav
- faster-whisper 多语言识别：auto, zh, en, ja, ko, es, fr, de
- pyannote.audio speaker diarization；未配置 `HF_TOKEN` 时自动跳过并在页面显示提示
- 英文到中文翻译：支持本地 Hugging Face 模型或 OpenAI-compatible API
- 按需翻译：每个转写片段和每个语段都可以单独翻译/重译，也可以选择目标语言后一键翻译当前缺失项
- 语段版输出：将细碎 timestamp segments 整理为更适合阅读的 paragraph transcript
- 播客笔记：复用 LLM/API 设置，将已完成任务整理为深潮 TechFlow 风格 Markdown 播客笔记
- 后台任务队列：queued, downloading, extracting_audio, transcribing, correcting, diarizing, aligning, translating, segmenting, completed, failed
- 转写结果查看、speaker 筛选、片段编辑、保存编辑
- 导出：txt, srt, vtt, json, markdown

## Docker 部署

```bash
cd voicescribe-webui
cp .env.example .env
docker compose up --build
```

服务启动后：

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

首次运行会下载 Whisper/pyannote 模型，镜像构建和第一次转写都可能比较慢。

## 本地开发

macOS 一键启动：

双击桌面的 `VoiceScribe WebUI.app`。它会自动启动后端和前端，然后打开 http://127.0.0.1:5173。

如果 `.app` 被 macOS 拦截或没有明显反应，双击桌面的 `VoiceScribe WebUI.command`。这个版本会打开 Terminal 并显示启动过程，排错更直观。

也可以用脚本启动或停止：

```bash
cd "/Users/silver/Documents/computer science/voicescribe-webui"
scripts/start-voicescribe.sh
scripts/stop-voicescribe.sh
```

Backend:

```bash
cd voicescribe-webui/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Worker 和 Redis:

```bash
redis-server
cd voicescribe-webui/backend
source .venv/bin/activate
celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --pool=solo
```

Frontend:

```bash
cd voicescribe-webui/frontend
npm install
npm run dev
```

如果没有 Redis，也可以在本地 `.env` 中设置 `RUN_TASKS_INLINE=true`，让 FastAPI 使用后台任务兜底执行。大文件仍推荐使用 Redis + Celery。

## 环境变量

复制 `.env.example` 为 `.env` 后按需修改：

```env
HF_TOKEN=
WHISPER_MODEL_SIZE=large-v3
WHISPER_DEVICE=auto
WHISPER_COMPUTE_TYPE=auto
WHISPER_INITIAL_PROMPT=
TRANSCRIPT_CORRECTION_MODE=rules
TRANSCRIPT_CORRECTION_BATCH_SIZE=30
TRANSLATION_MODE=off
TRANSLATION_TARGET_LANGUAGE=zh
TRANSLATION_LOCAL_MODEL=Helsinki-NLP/opus-mt-en-zh
TRANSLATION_API_BASE_URL=https://api.openai.com/v1
TRANSLATION_API_KEY=
TRANSLATION_API_MODEL=
PARAGRAPHING_MODE=rules
PARAGRAPHING_API_PROVIDER=openai
PARAGRAPHING_API_BASE_URL=https://api.openai.com/v1
PARAGRAPHING_API_KEY=
PARAGRAPHING_API_MODEL=
PARAGRAPHING_API_MAX_SENTENCES=220
PARAGRAPHING_SPLIT_ON_SPEAKER=true
```

`pyannote.audio` 的 diarization 模型需要 Hugging Face token。请先在 Hugging Face 页面接受 `pyannote/speaker-diarization-community-1` 的模型使用条款；如果使用 fine-grained token，还需要允许访问 public gated repositories。不要把 `HF_TOKEN` 写入代码或提交到仓库。

转写纠错：

- `WHISPER_INITIAL_PROMPT` 给 faster-whisper 传入专有名词、主题词或上下文提示，适合中文人名、术语、课程名、品牌名等。
- `TRANSCRIPT_CORRECTION_MODE=rules` 使用本地保守错词修正；`llm` 使用配置的 LLM/API 对转写片段按上下文纠错；`off` 关闭。
- `TRANSCRIPT_CORRECTION_BATCH_SIZE` 控制每次发给 LLM 的片段数量。LLM 纠错复用 `PARAGRAPHING_API_*`，未配置时可回退 `TRANSLATION_API_*`。

翻译模式：

- `TRANSLATION_MODE=local` 使用本地 Hugging Face translation pipeline，默认模型 `Helsinki-NLP/opus-mt-en-zh`，首次使用会下载模型。
- `TRANSLATION_MODE=api` 使用 OpenAI-compatible `/chat/completions` 接口，需要设置 `TRANSLATION_API_KEY` 和 `TRANSLATION_API_MODEL`。
- `TRANSLATION_MODE=off` 跳过翻译；如果任务勾选了翻译，会在任务详情显示提示。
- 任务详情页的“译为”下拉支持中文、英文、日文、韩文、西班牙文、法文和德文；本地翻译模式需要搭配对应方向的 Hugging Face 模型，API 模式更适合多语言切换。

语段分割模式：

- `PARAGRAPHING_MODE=rules` 使用本地规则分段，离线、快速、稳定。
- `PARAGRAPHING_MODE=llm` 使用配置的 LLM API 让模型给出语义段落边界。
- `PARAGRAPHING_API_PROVIDER=openai` 适用于 OpenAI-compatible 接口，例如 OpenAI、DeepSeek、Gemini OpenAI compatibility、OpenRouter。
- `PARAGRAPHING_API_PROVIDER=anthropic` 适用于 Anthropic Messages API，例如 Claude Haiku/Sonnet/Opus。
- `PARAGRAPHING_API_KEY` / `PARAGRAPHING_API_MODEL` 未填写时，会复用 `TRANSLATION_API_KEY` / `TRANSLATION_API_MODEL`。
- `PARAGRAPHING_SPLIT_ON_SPEAKER=true` 会把已知 speaker change 作为语段边界；页面里也可以临时打开或关闭。
- 页面顶部“设置”可以保存 LLM 分段 API key/model，并提供 OpenAI、DeepSeek V4、Claude、Gemini、OpenRouter 等预设；读取设置时不会把 key 回传到前端。
- 页面里的“语段版”支持选择 `规则` 或 `LLM` 后重新生成语段；手动选择 LLM 时，如果 API 配置缺失会显示错误。

播客笔记：

- 顶部“播客”栏可以选择已完成任务，填写标题、播客源、主持人、嘉宾、链接和章节列表后生成 Markdown 笔记。
- 任务详情页里的“播客笔记”页签可直接基于当前转写生成笔记。
- 播客笔记复用 `PARAGRAPHING_API_*`，未配置时回退 `TRANSLATION_API_*`；不会把 API key 回传到前端。
- 播客笔记会尝试从明确自我介绍中抽取 speaker 名字；没有可靠名字时按出现顺序使用 `speaker1`、`speaker2`。
- 如果 speaker 还是 `Speaker 1` 或 `SPEAKER_00` 这类标签，可以在主持人/嘉宾输入框中写 `Speaker 1=姓名` 或 `SPEAKER_00=姓名` 做映射。
- “自动映射 speaker 名字”可关闭；关闭后只使用手动映射，否则按 `speaker1`、`speaker2` 兜底。
- “联网补全源信息/日期”会用公开 URL 元数据和 LLM 尝试补全播客源、原标题和播出日期。
- “生成前清除历史”会在新笔记保存前删除当前任务的旧播客笔记；也可以用“清除历史笔记”按钮手动清空，减少本机数据库占用。
- “近期推荐”可输入关键词，也可粘贴最多 10 个视频/播客链接；时间跨度可在 1-30 天内调整，推荐条数可在 1-10 条内调整。系统会抓取公开元数据并搜索相似 YouTube 视频/播客；如果具体视频不足，会补充可打开的搜索入口，保证每次都有输出。
- 任务详情页的“删除转写内容”会清空转写片段、语段版和由转写生成的播客笔记，但保留任务记录和音频文件。

## 硬件建议

- CPU 可以运行，但转写速度较慢。
- 推荐 NVIDIA GPU，尤其是长音频或 `large-v3` 模型。
- `large-v3` 准确率更高，但内存和显存占用更大。
- `base` 或 `small` 更适合轻量部署和个人机器。
- Speaker diarization 需要额外模型、Hugging Face token 和更多计算资源。

## API 概览

- `POST /api/jobs/upload` 上传本地媒体文件
- `POST /api/jobs/from-url` 从公开 URL 创建任务
- `GET /api/jobs` 查看任务列表
- `GET /api/jobs/{job_id}` 查看任务详情
- `GET /api/jobs/{job_id}/segments` 查看转写片段
- `GET /api/jobs/{job_id}/paragraphs` 查看语段版转写
- `POST /api/jobs/{job_id}/paragraphs/regenerate` 重新生成语段版转写
- `GET /api/jobs/{job_id}/podcast-notes` 查看已生成播客笔记
- `POST /api/jobs/{job_id}/podcast-notes/generate` 生成播客笔记
- `DELETE /api/jobs/{job_id}/podcast-notes` 清除当前任务播客笔记历史
- `DELETE /api/jobs/{job_id}/transcript` 删除当前任务的转写片段、语段版和派生播客笔记
- `POST /api/podcast/recommendations` 根据关键词或最多 10 个链接推荐相似内容，支持 `days` 和 `max_results`
- `PATCH /api/jobs/{job_id}/segments/{segment_id}` 保存片段编辑
- `POST /api/jobs/{job_id}/retry` 重试任务
- `DELETE /api/jobs/{job_id}` 删除任务
- `GET /api/jobs/{job_id}/export?format=txt|srt|vtt|json|md|paragraph_md|paragraph_json` 导出结果

## 法律与版权

URL 导入使用 `yt-dlp` 处理公开可访问媒体。应用不会传递 cookie、登录凭据、DRM 绕过参数或付费墙绕过逻辑。请只处理你拥有权利、获得授权、或平台条款允许处理的内容。

Bilibili 支持使用公开页面解析，并附带浏览器式 User-Agent、Referer 与语言头来降低误拦截概率。如果页面需要登录、会员、cookie 或地区权限，应用会返回清晰错误，不会绕过限制。

## 常见问题

**缺少 `HF_TOKEN` 会怎样？**

任务会继续转写，只跳过 speaker diarization，并在任务详情页显示提示。

**为什么第一次转写很慢？**

模型需要下载和加载，`large-v3` 尤其明显。后续任务通常会更快。

**URL 导入失败怎么办？**

确认链接是公开可访问内容，并且不是登录墙、付费墙或 DRM 内容。不同网站适配程度取决于 `yt-dlp`。

**SRT/VTT 是否可用？**

已实现基础导出。更复杂的字幕断句、字级时间戳和翻译字幕可以继续在 `backend/app/services/exporter.py` 扩展。
