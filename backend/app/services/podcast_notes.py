import json
import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app import models

logger = logging.getLogger(__name__)
from app.config import get_settings
from app.services.downloader import _anti_bot_options, validate_public_http_url, yt_dlp_command


@dataclass
class PodcastNoteDraft:
    title: str | None
    markdown: str
    metadata_json: str


PODCAST_NOTES_SKILL_RULES = """
# 播客笔记整理 Skill

## 你的任务

将原始播客逐字稿整理成标准格式的中文播客笔记。输出必须包含：元数据头部 → 要点总结 → 精彩观点摘要 → 精彩片段 → 完整对话正文 → 原文链接。

---

## 输出格式（严格遵循此示例结构）

```
播客标题纯文本

整理 & 编译：深潮TechFlow
[图片]
嘉宾：嘉宾姓名，职位/身份
主持人：主持人姓名
播客源：播客节目或频道名称
原标题：播客/视频原始标题
播出日期：YYYY年M月D日

要点总结
3-5句中文概括段落，不用 bullet points，直接写成一整段。

精彩观点摘要
关于第一个主题
- "精彩观点原文引用，中文全角引号。"
- "另一条观点。"

关于第二个主题
- "精彩观点。"

## 精彩片段
**Eric Trump**：
这是一段精选的精彩对话。嘉宾姓名单独一行，内容另起一行。

**主持人 Bonnie**：主持人的提问和内容在同一行。

## 第一个章节标题
**主持人 David**：主持人的内容和姓名标签在同一行。

**Eric Trump**：
嘉宾的说话内容另起一行。同一说话人的连续多段内容合并在一起。

**主持人 Bonnie**：第二个问题。

**Eric Trump**：
第二个回答。

## 第二个章节标题
...（按章节顺序，直到全文结束）

原文链接：https://...
```

---

## 格式规则（严格遵守）

### 元数据
- 第一行：纯文本标题（不加 # 前缀），空一行后接元数据
- `[图片]` 必须出现
- 没有嘉宾时写 `嘉宾：无`（不省略此字段）

### 要点总结
- 一个自然段，3-5 句中文，不用 bullet points

### 精彩观点摘要
- 按主题分组，每组标题：`关于 [主题]`
- 每条：`- "观点原文"`（中文全角引号），**不加**说话人姓名
- 每组 1-4 条

### 精彩片段
- 正文前的高光片段：`## 精彩片段`
- 挑选 2-5 轮最精彩的简短对话

### 正文章节
- 章节标题：`## 章节名称`（Markdown H2）
- 严格按照提供的 chapter_items 顺序，不自行增减
- 章节之间空一行

### 说话人格式
- **主持人**：`**主持人 Name**：内容同行`
- **嘉宾**：`**Name**：` 单独一行，内容另起一行
- 同一说话人连续多段合并
- 切换说话人时空一行

---

## 处理步骤

### 第一步：章节划分
- 严格按照 chapter_items 的小标题和时间戳划分
- 每个章节只处理该时间范围内的内容

### 第二步：说话人识别
判断依据（按优先级）：
1. 上下文连贯性：同一话题的连续表达通常是同一人
2. 问答结构：主持人提问/引导，嘉宾展开回答
3. 第一人称陈述：结合嘉宾背景判断
4. 称谓与回应："你刚才提到……"表示说话人切换
5. 使用 speaker_name_map 中提供的映射

### 第三步：逐章节处理（重要）
长逐字稿必须按章节逐一处理，不得一次性处理全文：
1. 取出第一个章节的原文段落
2. 完成该章节的说话人识别 → 翻译 → 提炼精彩观点
3. 追加到草稿
4. 再取下一个章节，重复

### 第四步：翻译与文字处理

**必须做的**：
- 翻译成自然流畅的中文——读起来像中文原创，不是翻译稿
- 口语长段拆分为合理句子
- 使用中文全角标点（，。！？；：""''……——）
- 修正明显语音识别错误和口误
- 保留专有名词原文或通用译名（Bitcoin→比特币，Ethereum→以太坊）
- 合并简短互动回应：单独的 "Yeah."、"Right."、"嗯。"、"对。" 合并到上下文或省略，不单独成段

**绝对不能做的**：
- ❌ 不得翻译英文口语填充词：like, uh, um, you know（直接忽略）
- ❌ "right?" 根据语境忽略，不译为"对吧"
- ❌ "I mean" 根据语境处理，不机械译为"我的意思是"
- ❌ "sort of", "kind of" 视语境处理
- ❌ 不得字对字翻译，导致中文出现大量"就是""然后然后""像像像"

**广告/赞助**：跳过，不出现在正文中。

### 第五步：提炼精彩观点
每个章节提炼 1-3 条最有代表性的观点，用于"精彩观点摘要"：
- 来自原文，可做最小润色
- 脱离上下文仍能独立理解
- 优先嘉宾的洞见、金句、反常识观点

### 第六步：撰写要点总结
用 3-5 句概括整期核心内容，帮助读者快速判断是否值得深读。

---

## 内容完整性（最高优先级）

- **禁止概括代替翻译**：每一个论点、例子、推理都必须完整出现在正文中
- **禁止以篇幅为由跳过内容**：无论章节多长，必须完整整理
- **禁止合并不相关内容**：不同观点不得压缩合并
- **字数参照**：整理后中文字数 ≈ 原文英文单词数 × 0.6~0.8。如某章节过短，说明有遗漏

---

## 严禁杜撰（反幻觉）

- 输出中每一句对话必须能在原始逐字稿中找到来源
- 不得凭记忆、推断或感觉补充内容
- 翻译改写幅度过大可能导致无意识杜撰——如意思已偏离原文，重新参照原文
- speaker_name_map 只有 speaker1/speaker2 泛化标签时，保持它们，不编造真实姓名

**每个章节完成后自检**：本章节正文中有没有原文未提及的内容？有则删除，替换为逐字稿原文。

---

## 质量检查清单

完成后自检：
- [ ] 章节数量与 chapter_items 一致，没有多出或缺少
- [ ] 无 "like/uh/um/you know" 的残留翻译
- [ ] 无单独 "是的""对""嗯" 的段落
- [ ] 翻译通顺自然，无翻译腔
- [ ] 要点总结是段落而非 bullet points
- [ ] 主持人 `**主持人 Name**：` 内容同行；嘉宾 `**Name**：` 内容另起一行
- [ ] 切换说话人时空一行
- [ ] 所有实质性观点均在输出中呈现
- [ ] 无杜撰或凭空添加的内容
- [ ] 各章节内容对应正确时间段
- [ ] 原文链接在最后
- [ ] 不输出代码围栏或 JSON
""".strip()


def _format_timestamp(seconds: float) -> str:
    value = max(0, int(seconds))
    hours = value // 3600
    minutes = (value % 3600) // 60
    remaining = value % 60
    return f"{hours:02d}:{minutes:02d}:{remaining:02d}"


def _clean_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _clean_outline(text: str | None) -> str:
    lines = []
    for line in (text or "").replace("\\n", "\n").splitlines():
        cleaned = _clean_text(line)
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def _chapter_items_from_outline(outline: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for index, line in enumerate(outline.splitlines(), start=1):
        match = re.match(r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+?)\s*$", line)
        if match:
            timestamp = match.group(1)
            title = match.group(2).strip()
        else:
            timestamp = "00:00:00" if index == 1 else ""
            title = line.strip()
        if title:
            items.append({"timestamp": timestamp, "title": title})
    return items


def _is_generic_speaker_label(value: str | None) -> bool:
    label = _clean_text(value)
    if not label or label.upper() == "UNKNOWN":
        return True
    # Match SPEAKER_00, SPEAKER 00, speaker_00, Speaker 1, speaker1, SPEAKER00, etc.
    if bool(re.fullmatch(r"(?:SPEAKER[_\s-]?|Speaker\s*)\d+", label, flags=re.IGNORECASE)):
        return True
    # Match bare digits like "0", "1", "00", "01"
    if bool(re.fullmatch(r"\d{1,3}", label)):
        return True
    return False


def _speaker_labels(segments: list[models.TranscriptSegment]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for segment in segments:
        label = _clean_text(segment.speaker) or "UNKNOWN"
        if label not in seen:
            labels.append(label)
            seen.add(label)
    return labels or ["UNKNOWN"]


def _parse_explicit_speaker_mappings(*texts: str | None) -> dict[str, str]:
    """Parse explicit speaker mappings from user input.

    Supports formats like:
      - SPEAKER_00=姓名
      - Speaker 1=姓名
      - speaker_00: 姓名
      - SPEAKER_00：姓名（职位）
    """
    mappings: dict[str, str] = {}
    # Broader pattern: match "Speaker 1=Name" or "SPEAKER_00：姓名" with optional role/position after name
    pattern = re.compile(
        r"\b(SPEAKER[_\s-]?\d+|Speaker\s*\d+|speaker[_\s-]?\d+)\b\s*[=:：]\s*([^,，;\n；]+?)(?:[，,](?:[^=:：\n])*)?$",
        re.IGNORECASE | re.MULTILINE,
    )
    for text in texts:
        for raw_label, raw_name in pattern.findall(text or ""):
            label = raw_label.replace(" ", "_").replace("-", "_").upper()
            # Strip trailing role/position in parens
            name = _clean_text(re.sub(r"[（(][^)）]*[)）]$", "", raw_name)).strip("：:，,。.;； ")
            if name:
                mappings[label] = name
    return mappings


def _speaker_mapping_key(label: str) -> str:
    return re.sub(r"[_\s-]+", "_", label.strip()).upper()


def _candidate_from_intro(text: str) -> str | None:
    """Extract a likely speaker name from self-introduction or third-party introduction text."""
    normalized = _clean_text(text)
    reject_fragments = (
        "一个", "一名", "今天", "这里", "来自", "觉得", "认为",
        "going", "not", "really", "very", "just", "maybe",
        "大家好", "欢迎", "各位", "朋友",
    )

    patterns_cn = [
        # Self-intro: "我是/我叫/我是主持人/etc"
        r"(?:我是|我叫|我是主持人|我是嘉宾|这里是|我是[^\s,，。.!！?？]{0,6}的)\s*([一-鿿A-Za-z][一-鿿A-Za-z·.\s-]{1,24})(?:[，,。.、!！?？\s]|$)",
        # Third-party: "这位是..."
        r"这位是\s*([一-鿿A-Za-z][一-鿿A-Za-z·.\s-]{1,24})(?:[，,。.、!！?？\s]|$)",
        # "今天我们请到了..."
        r"今天我们?请到[了]?\s*([一-鿿A-Za-z][一-鿿A-Za-z·.\s-]{1,24})(?:[，,。.、!！?？\s]|$)",
        # "欢迎XXX来到/做客"
        r"欢迎\s*([一-鿿A-Za-z][一-鿿A-Za-z·.\s-]{1,24})(?:来到|做客|参加|加入|光临)",
        # "有请..."
        r"有请\s*([一-鿿A-Za-z][一-鿿A-Za-z·.\s-]{1,24})(?:[，,。.、!！?？\s]|$)",
    ]
    patterns_en = [
        r"(?:my name is|this is|i['’]?m|i am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})(?:[,.!?]|$)",
        r"joining us\s+(?:today\s+)?(?:is|are)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})",
        r"please welcome\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})",
    ]

    for pattern in patterns_cn + patterns_en:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        candidate = _clean_text(match.group(1)).strip("：:，,。.;； ")
        if not candidate:
            continue
        if not re.search(r"[一-鿿A-Za-z]", candidate):
            continue
        if len(candidate) > 30:
            continue
        if any(fragment.lower() in candidate.lower() for fragment in reject_fragments):
            continue
        if re.fullmatch(r"[一-鿿]{2,4}", candidate):
            return candidate
        if re.fullmatch(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}", candidate):
            return candidate
    return None


def _build_speaker_name_map(
    segments: list[models.TranscriptSegment],
    host: str | None = None,
    guests: str | None = None,
    auto_detect_names: bool = True,
) -> dict[str, str]:
    """Build a mapping from raw speaker labels to display names.

    Priority order:
    1. Explicit mappings from host/guests fields (e.g. "SPEAKER_00=Alice")
    2. Non-generic labels from diarization (e.g. pyannote sometimes returns actual names)
    3. Auto-detect from self-introduction text (e.g. "Hi I'm Alice, welcome to...")
    4. Fallback: speaker1, speaker2, ...
    """
    labels = _speaker_labels(segments)
    explicit = _parse_explicit_speaker_mappings(host, guests)
    by_label: dict[str, list[str]] = {label: [] for label in labels}
    for segment in segments:
        label = _clean_text(segment.speaker) or "UNKNOWN"
        if label in by_label and len(by_label[label]) < 60:
            by_label[label].append(segment.text)

    result: dict[str, str] = {}
    used_names: set[str] = set()

    for index, label in enumerate(labels, start=1):
        key = _speaker_mapping_key(label)

        # 1. Explicit user-provided mapping
        if key in explicit:
            result[label] = explicit[key]
        # 2. Non-generic label (e.g. pyannote returned a real name or YouTube captions gave a name)
        elif auto_detect_names and not _is_generic_speaker_label(label):
            result[label] = label
        # 3. Auto-detect from self-introduction
        elif auto_detect_names:
            # Try all text samples from this speaker for name candidates
            inferred = None
            for text in by_label.get(label, []):
                inferred = _candidate_from_intro(text)
                if inferred:
                    break
            # If no self-intro found, check if label appears as a name in other speakers' intro text
            if not inferred:
                for other_label, texts in by_label.items():
                    if other_label == label:
                        continue
                    for text in texts:
                        inferred = _candidate_from_intro(text)
                        if inferred and index > 1:
                            break
                    if inferred:
                        break
            result[label] = inferred or f"speaker{index}"
        # 4. Auto-detect off: use generic fallback
        else:
            result[label] = f"speaker{index}"

        # Deduplicate: if two labels map to the same name, keep first, fallback to generics for later ones
        if result[label] in used_names:
            # Try to find an alternative candidate
            alt = None
            for text in by_label.get(label, [])[1:]:
                alt = _candidate_from_intro(text)
                if alt and alt not in used_names:
                    break
            if alt and alt not in used_names:
                result[label] = alt
            else:
                result[label] = f"speaker{index}"
        used_names.add(result[label])

    # Post-process: if host is a plain name (not a mapping), use it for the first speaker
    clean_host = _clean_text(host)
    if clean_host and not _parse_explicit_speaker_mappings(host):
        first_label = labels[0] if labels else None
        if first_label and _is_generic_speaker_label(result.get(first_label, "")):
            result[first_label] = clean_host

    return result


def _strip_markdown_fences(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown|md)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _strip_json_fences(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json_payload(content: str) -> Any:
    text = _strip_json_fences(content)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start_candidates = [index for index in (text.find("{"), text.find("[")) if index >= 0]
        if not start_candidates:
            raise
        start = min(start_candidates)
        end = max(text.rfind("}"), text.rfind("]"))
        if end <= start:
            raise
        return json.loads(text[start : end + 1])


def _format_source_date(value: str | int | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{8}", text):
        return f"{int(text[:4])} 年 {int(text[4:6])} 月 {int(text[6:8])} 日"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        year, month, day = text.split("-")
        return f"{int(year)} 年 {int(month)} 月 {int(day)} 日"
    return text


def _looks_empty_or_placeholder(value: str | None, source_url: str | None = None) -> bool:
    text = _clean_text(value)
    if not text or text == "未填写":
        return True
    return bool(source_url and text == source_url)


def _fetch_source_metadata(source_url: str | None) -> dict[str, Any]:
    url = _clean_text(source_url)
    if not url:
        return {}
    validate_public_http_url(url)
    command = [
        *yt_dlp_command(),
        "--dump-single-json",
        "--skip-download",
        "--no-playlist",
        "--no-warnings",
        *_anti_bot_options(url),
        url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Could not fetch source metadata")
    raw = json.loads(result.stdout)
    return {
        "url": url,
        "webpage_url": raw.get("webpage_url") or raw.get("original_url") or url,
        "title": raw.get("title"),
        "fulltitle": raw.get("fulltitle"),
        "channel": raw.get("channel"),
        "uploader": raw.get("uploader"),
        "uploader_id": raw.get("uploader_id"),
        "creator": raw.get("creator"),
        "series": raw.get("series"),
        "playlist_title": raw.get("playlist_title"),
        "episode": raw.get("episode"),
        "upload_date": _format_source_date(raw.get("upload_date")),
        "release_date": _format_source_date(raw.get("release_date")),
        "timestamp": raw.get("timestamp"),
        "description": _clean_text(raw.get("description"))[:1200],
    }


def _merge_metadata(current: dict[str, Any], discovered: dict[str, Any], source_url: str | None) -> dict[str, Any]:
    merged = dict(current)
    for key in ("podcast_source", "original_title", "published_date"):
        value = _clean_text(discovered.get(key))
        if value and _looks_empty_or_placeholder(str(merged.get(key, "")), source_url):
            merged[key] = value
    value = _clean_text(discovered.get("source_url") or discovered.get("webpage_url"))
    if value and _looks_empty_or_placeholder(str(merged.get("source_url", "")), source_url):
        merged["source_url"] = value
    return merged


def _normalize_source_metadata_with_llm(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    current_metadata: dict[str, Any],
    raw_metadata: dict[str, Any],
) -> dict[str, str]:
    system_prompt = (
        "You normalize public podcast/video metadata. Use only the provided raw metadata. "
        "Return JSON only with keys podcast_source, original_title, published_date, source_url. "
        "Do not invent dates or names. If unknown, return an empty string. Format date like 2026 年 5 月 12 日."
    )
    user_prompt = {
        "current_metadata": current_metadata,
        "raw_source_metadata": raw_metadata,
    }
    content = (
        _anthropic_completion(base_url, api_key, model, system_prompt, user_prompt)
        if provider == "anthropic"
        else _openai_compatible_completion(base_url, api_key, model, system_prompt, user_prompt)
    )
    payload = _extract_json_payload(content)
    if not isinstance(payload, dict):
        return {}
    return {
        key: _clean_text(payload.get(key))
        for key in ("podcast_source", "original_title", "published_date", "source_url")
        if _clean_text(payload.get(key))
    }


def _api_config() -> tuple[str, str, str, str]:
    settings = get_settings()
    provider = settings.paragraphing_api_provider.lower().strip()
    if provider not in {"openai", "anthropic"}:
        provider = "openai"
    base_url = (settings.paragraphing_api_base_url or settings.translation_api_base_url).rstrip("/")
    api_key = settings.paragraphing_api_key or settings.translation_api_key
    model = settings.paragraphing_api_model or settings.translation_api_model

    if not api_key:
        raise RuntimeError("PARAGRAPHING_API_KEY or TRANSLATION_API_KEY is required for podcast notes")
    if not model:
        raise RuntimeError("PARAGRAPHING_API_MODEL or TRANSLATION_API_MODEL is required for podcast notes")
    return provider, base_url, api_key, model


def _openai_compatible_completion(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: dict[str, Any],
) -> str:
    response = httpx.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": 0.2,
            "max_tokens": 20000,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
            ],
        },
        timeout=420,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _anthropic_completion(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: dict[str, Any],
) -> str:
    response = httpx.post(
        f"{base_url}/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 20000,
            "temperature": 0.2,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
            ],
        },
        timeout=420,
    )
    response.raise_for_status()
    content = response.json().get("content", [])
    return "\n".join(
        str(block.get("text", ""))
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()


def _segment_lines(segments: list[models.TranscriptSegment], speaker_name_map: dict[str, str]) -> list[str]:
    lines: list[str] = []
    for segment in segments:
        raw_speaker = _clean_text(segment.speaker) or "UNKNOWN"
        speaker = speaker_name_map.get(raw_speaker, raw_speaker)
        text = _clean_text(segment.text)
        if not text:
            continue
        translated = _clean_text(segment.translated_text)
        suffix = f"\n    translated: {translated}" if translated else ""
        lines.append(f"[{_format_timestamp(segment.start)}-{_format_timestamp(segment.end)}] {speaker}: {text}{suffix}")
    return lines


def _replace_raw_speaker_labels(markdown: str, speaker_name_map: dict[str, str]) -> str:
    result = markdown
    for raw_label, display_name in sorted(speaker_name_map.items(), key=lambda item: len(item[0]), reverse=True):
        if raw_label and display_name and raw_label != display_name:
            result = re.sub(rf"\b{re.escape(raw_label)}\b", display_name, result)
    return result


def _auto_chapter_outline(
    paragraphs: list[models.TranscriptParagraph],
    segments: list[models.TranscriptSegment],
) -> str:
    if paragraphs:
        target_count = min(10, max(4, round((paragraphs[-1].end - paragraphs[0].start) / 360)))
        step = max(1, round(len(paragraphs) / target_count))
        selected = paragraphs[::step][:target_count]
        if selected and selected[0].start > 1 and paragraphs[0] not in selected:
            selected.insert(0, paragraphs[0])
        lines = []
        for index, paragraph in enumerate(selected, start=1):
            title = _clean_text(paragraph.title or paragraph.summary)
            if not title:
                title = f"第{index}部分"
            lines.append(f"{_format_timestamp(paragraph.start)} {title[:80]}")
        return "\n".join(lines)

    if not segments:
        return "00:00:00 正文"
    return f"{_format_timestamp(segments[0].start)} 正文"


def _metadata_payload(
    *,
    podcast_source: str | None,
    original_title: str | None,
    published_date: str | None,
    host: str | None,
    guests: str | None,
    source_url: str | None,
    chapter_outline: str | None,
    include_full_dialogue: bool,
) -> dict[str, Any]:
    return {
        "podcast_source": _clean_text(podcast_source) or "未填写",
        "original_title": _clean_text(original_title) or "未填写",
        "published_date": _clean_text(published_date) or "未填写",
        "host": _clean_text(host) or "未填写",
        "guests": _clean_text(guests) or "无",
        "source_url": _clean_text(source_url) or "未填写",
        "chapter_outline": chapter_outline or "",
        "include_full_dialogue": include_full_dialogue,
    }


def generate_podcast_note(
    *,
    segments: list[models.TranscriptSegment],
    paragraphs: list[models.TranscriptParagraph],
    podcast_source: str | None = None,
    original_title: str | None = None,
    published_date: str | None = None,
    host: str | None = None,
    guests: str | None = None,
    source_url: str | None = None,
    chapter_outline: str | None = None,
    auto_map_speakers: bool = True,
    lookup_source_metadata: bool = False,
    include_full_dialogue: bool = True,
) -> PodcastNoteDraft:
    """Generate a Chinese podcast note markdown document from transcript rows."""
    if not segments:
        raise ValueError("No transcript segments available for podcast notes")

    provider, base_url, api_key, model = _api_config()
    chapters = _clean_outline(chapter_outline)
    if not chapters:
        chapters = _auto_chapter_outline(paragraphs, segments)
    chapter_items = _chapter_items_from_outline(chapters)
    speaker_name_map = _build_speaker_name_map(
        segments,
        host=host,
        guests=guests,
        auto_detect_names=auto_map_speakers,
    )
    speaker_labels = _speaker_labels(segments)
    metadata_host = host
    metadata_guests = guests
    if not _clean_text(metadata_host) and speaker_labels:
        metadata_host = speaker_name_map.get(speaker_labels[0], "speaker1")
    if not _clean_text(metadata_guests) and len(speaker_labels) > 1:
        metadata_guests = "；".join(
            speaker_name_map.get(label, f"speaker{index}")
            for index, label in enumerate(speaker_labels[1:], start=2)
        )

    metadata = _metadata_payload(
        podcast_source=podcast_source,
        original_title=original_title,
        published_date=published_date,
        host=metadata_host,
        guests=metadata_guests,
        source_url=source_url,
        chapter_outline=chapters,
        include_full_dialogue=True,
    )
    metadata["speaker_name_map"] = speaker_name_map
    metadata["auto_map_speakers"] = auto_map_speakers
    metadata["lookup_source_metadata"] = lookup_source_metadata

    source_metadata: dict[str, Any] = {}
    if lookup_source_metadata and _clean_text(source_url):
        source_metadata = _fetch_source_metadata(source_url)
        discovered = {
            "podcast_source": source_metadata.get("channel")
            or source_metadata.get("uploader")
            or source_metadata.get("creator")
            or source_metadata.get("series")
            or source_metadata.get("playlist_title"),
            "original_title": source_metadata.get("title") or source_metadata.get("fulltitle") or source_metadata.get("episode"),
            "published_date": source_metadata.get("release_date") or source_metadata.get("upload_date"),
            "source_url": source_metadata.get("webpage_url") or source_url,
        }
        try:
            normalized = _normalize_source_metadata_with_llm(
                provider=provider,
                base_url=base_url,
                api_key=api_key,
                model=model,
                current_metadata=metadata,
                raw_metadata=source_metadata,
            )
            discovered.update(normalized)
        except Exception:
            pass
        metadata = _merge_metadata(metadata, discovered, source_url)
        metadata["speaker_name_map"] = speaker_name_map
        metadata["auto_map_speakers"] = auto_map_speakers
        metadata["lookup_source_metadata"] = lookup_source_metadata
        metadata["source_metadata"] = source_metadata

    system_prompt = (
        "You are the podcast-notes skill inside VoiceScribe WebUI. "
        "Below are the authoritative SKILL RULES — follow them exactly. "
        "Your output must match the format example. Process chapter by chapter, not all at once. "
        "Translate naturally into Chinese. Never fabricate content. "
        "Every sentence must be traceable to the source transcript.\n\n"
        f"{PODCAST_NOTES_SKILL_RULES}"
    )
    output_contract = [
        "Follow the SKILL RULES format precisely.",
        "Plain-text title → blank line → metadata block (with [图片], 嘉宾：无 if no guest).",
        "要点总结: one paragraph, 3-5 sentences, no bullets.",
        "精彩观点摘要: 关于 topic groups, - \"quote\" format, NO speaker attribution.",
        "## 精彩片段 section: 2-5 highlighted exchanges before full dialogue.",
        "Body chapters: ## Title H2, in chapter_items order, blank line between chapters.",
        "Host: **主持人 Name**：content SAME line.",
        "Guest: **Name**：on own line, content NEXT line.",
        "Blank line between speaker turns.",
        "No filler words (like/uh/um/you know). Merge single-word acknowledgments.",
        "No summarization-as-translation. Every argument/example must appear in full.",
        "Self-check each chapter: nothing fabricated, nothing skipped.",
        "End with 原文链接：[URL].",
    ]

    user_prompt = {
        "metadata": metadata,
        "chapter_outline": chapters,
        "chapter_items": chapter_items,
        "speaker_name_map": speaker_name_map,
        "source_metadata": source_metadata,
        "output_contract": output_contract,
        "speaker_notes": [
            "Apply speaker_name_map strictly. If it says Speaker 1 → 主持人 Bonnie, use that exact name.",
            "If speaker_name_map has only speaker1, speaker2 generic labels, use those as-is — do not invent real names.",
            "To identify who is speaking: follow context continuity, Q&A structure (host asks, guest answers), first-person statements, and cross-references like 'you just mentioned'.",
            "The first speaker in the transcript is typically the host unless metadata indicates otherwise.",
            "When transcript has >> symbols, treat them as possible speaker change points.",
        ],
        "transcript": _segment_lines(segments, speaker_name_map),
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    content = (
        _anthropic_completion(base_url, api_key, model, system_prompt, user_prompt)
        if provider == "anthropic"
        else _openai_compatible_completion(base_url, api_key, model, system_prompt, user_prompt)
    )
    markdown = _replace_raw_speaker_labels(_strip_markdown_fences(content), speaker_name_map)
    if not markdown:
        raise ValueError("Podcast note generation returned empty content")
    return PodcastNoteDraft(
        title=metadata["original_title"] if metadata["original_title"] != "未填写" else None,
        markdown=markdown,
        metadata_json=json.dumps(metadata, ensure_ascii=False),
    )


def autofill_speakers(
    job: models.Job,
    segments: list[models.TranscriptSegment],
) -> dict[str, str]:
    """Auto-fill host and guest speaker names from source metadata + transcript.

    Returns dict with keys "host" (；-separated for multi-host), "guests" (newline-separated),
    and metadata fields.
    """
    hosts: list[str] = []
    guests_list: list[str] = []

    # 1. Source metadata via yt-dlp
    source_metadata: dict[str, Any] = {}
    if job.source_url and _clean_text(job.source_url):
        try:
            source_metadata = _fetch_source_metadata(job.source_url)
        except Exception:
            logger.debug("autofill_speakers: yt-dlp metadata fetch failed, continuing without it")

    channel_host = ""
    description = ""
    if source_metadata:
        channel_host = _clean_text(
            source_metadata.get("channel")
            or source_metadata.get("uploader")
            or source_metadata.get("creator")
            or source_metadata.get("series")
            or ""
        )
        description = _clean_text(source_metadata.get("description") or "")

    # 2. LLM analysis: identify ALL speakers from transcript content + description
    try:
        provider, base_url, api_key, model = _api_config()
    except Exception:
        provider = None

    if provider and segments:
        # Build a sample of the transcript for the LLM to analyze
        sample_lines: list[str] = []
        for s in segments[:30]:
            sample_lines.append(f"[{_format_timestamp(s.start)}] {_clean_text(s.text)[:200]}")
        transcript_sample = "\n".join(sample_lines)

        llm_system = (
            "You analyze a podcast transcript to identify every speaker. "
            "Look for self-introductions (\"I'm X\", \"my name is X\", \"我是X\"), "
            "third-party introductions (\"joining us is X\", \"welcome X\", \"今天请到了X\"), "
            "and conversational roles (who asks questions vs who gives long answers). "
            "A show may have MULTIPLE hosts and MULTIPLE guests. "
            "Hosts: introduce topics, ask questions, facilitate the conversation. "
            "Guests: share expertise, answer questions, tell their story. "
            "Return JSON only: {\"hosts\": [\"name\"], \"guests\": [\"name\"]}. "
            "Use the name as spoken (e.g. \"David\" not \"David Lin\" unless the full name is clearly stated). "
            "If no one is clearly identified, return empty arrays. Do NOT invent names."
        )
        llm_prompt: dict[str, Any] = {
            "transcript_sample": transcript_sample[:4000],
            "video_description": description[:1000] if description else "",
            "instruction": "Identify every host and guest from the transcript content. Look for self-introductions and third-party introductions.",
        }
        try:
            content = (
                _anthropic_completion(base_url, api_key, model, llm_system, llm_prompt)
                if provider == "anthropic"
                else _openai_compatible_completion(base_url, api_key, model, llm_system, llm_prompt)
            )
            payload = _extract_json_payload(content)
            if isinstance(payload, dict):
                def _parse_names(raw: Any) -> list[str]:
                    if isinstance(raw, str):
                        return [_clean_text(raw)] if _clean_text(raw) else []
                    if isinstance(raw, list):
                        return [_clean_text(n) for n in raw if _clean_text(n)]
                    return []

                llm_hosts = _parse_names(payload.get("hosts") or payload.get("host"))
                llm_guests = _parse_names(payload.get("guests") or payload.get("guest"))

                if llm_hosts:
                    hosts = llm_hosts
                if llm_guests:
                    guests_list = llm_guests
        except Exception:
            logger.debug("autofill_speakers: LLM transcript analysis failed, trying description fallback")

    # 3. Fallback: LLM description-only analysis (if transcript analysis didn't find anything)
    if not hosts and not guests_list and description and provider:
        llm_system2 = (
            "Extract host and guest names from this video description. "
            "Return JSON only: {\"hosts\": [\"name\"], \"guests\": [\"name\"]}. "
            "Empty arrays if unclear. Do not invent."
        )
        try:
            content2 = (
                _anthropic_completion(base_url, api_key, model, llm_system2, {"description": description})
                if provider == "anthropic"
                else _openai_compatible_completion(base_url, api_key, model, llm_system2, {"description": description})
            )
            payload2 = _extract_json_payload(content2)
            if isinstance(payload2, dict):
                for h in (payload2.get("hosts") or payload2.get("host") or []):
                    h = _clean_text(h) if isinstance(h, str) else ""
                    if h and h not in hosts:
                        hosts.append(h)
                for g in (payload2.get("guests") or payload2.get("guest") or []):
                    g = _clean_text(g) if isinstance(g, str) else ""
                    if g and g not in guests_list:
                        guests_list.append(g)
        except Exception:
            logger.debug("autofill_speakers: LLM description fallback also failed")

    # 4. Fallback: regex-based transcript detection for any missed names
    if segments:
        speaker_name_map = _build_speaker_name_map(
            segments, host=None, guests=None, auto_detect_names=True,
        )
        if speaker_name_map:
            for label in _speaker_labels(segments):
                display = speaker_name_map.get(label, label)
                if display and not _is_generic_speaker_label(display):
                    if display not in hosts and display not in guests_list:
                        if not hosts:
                            hosts.append(display)
                        else:
                            guests_list.append(display)

    # 5. Last resort: nothing found
    if not hosts and not guests_list:
        logger.info("autofill_speakers: no speakers identified for job %s", job.id)

    logger.info(
        "autofill_speakers job=%s hosts=%r guests=%r",
        job.id,
        hosts,
        guests_list,
    )

    # 5. Extract metadata
    published_date = ""
    if source_metadata:
        published_date = (
            source_metadata.get("release_date")
            or source_metadata.get("upload_date")
            or ""
        )

    original_title = ""
    if source_metadata:
        original_title = _clean_text(
            source_metadata.get("title")
            or source_metadata.get("fulltitle")
            or ""
        )

    return {
        "host": "；".join(hosts),
        "guests": "\n".join(guests_list),
        "podcast_source": channel_host or "",
        "original_title": original_title,
        "published_date": published_date,
        "source_url": source_metadata.get("webpage_url") or _clean_text(job.source_url or "") or "",
    }
