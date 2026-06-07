import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app import models
from app.config import get_settings
from app.services.downloader import _site_options, validate_public_http_url, yt_dlp_command


@dataclass
class PodcastNoteDraft:
    title: str | None
    markdown: str
    metadata_json: str


PODCAST_NOTES_SKILL_RULES = """
# 播客笔记整理 Skill - official output format

你必须模仿用户提供的 podcast-notes skill 与 outputs/*.md 成品格式，而不是输出普通摘要或媒体解读文章。

最终 Markdown 结构：
1. 元数据头部（每行一条，不要加粗）：
   整理 & 编译：深潮TechFlow
   嘉宾：[嘉宾姓名，职位/身份]；[嘉宾2姓名，职位/身份]
   主持人：[主持人姓名]
   播客源：[播客节目或频道名称]
   原标题：[播客/视频原始标题]
   播出日期：[YYYY年M月D日]
   如果没有嘉宾，省略"嘉宾："行，不要写"嘉宾：无"。不要添加 `[图片]` 占位。
2. 空一行后写 `要点总结`，下一段用 3-5 句中文概括整期核心内容，不用 bullet points。
3. 空一行后写 `精彩观点摘要`。按章节分组，每组格式为 `（章节小标题）`，组内用 `* "观点原文" ——说话人姓名` 列出 1-3 条精彩观点。
4. 空一行后写完整对话正文。正文按 chapter_items 顺序逐章输出：
   - 章节标题：只写小标题纯文本本身，不要用 `##`、`###`、`**加粗**` 或 bullet。
   - 章节标题后直接接第一段对话，中间不空行。
5. 最后一行：`原文链接：[URL]`；无 URL 则写 `原文链接：暂无`。

正文说话人格式：
- 主持人：`主持人 [姓名]：[内容同行]` — 主持人标签、姓名和内容必须在同一行，不换行。
- 嘉宾/非主持人：`[姓名]：` 单独占一行，说话内容另起一行。
- 同一说话人连续多段内容合并为一段；切换说话人时才另起段。
- 正文段落之间不添加空白行。
- 不要使用 `**主持人 XXX**：` 或 `**嘉宾**：` 这类加粗 speaker 标签。

章节规则：
- 严格使用 chapter_items 中提供的小标题和顺序。不得自行增减或重排章节。
- 每个章节只整理该章节时间范围内的内容，不能跨章节串内容。
- 如果 chapter_items 为空，整个正文作为一个无标题章节。

内容处理：
- 英文逐字稿翻译成自然流畅的中文，要像中文原创文章，不要翻译腔。
- 删除口语填充词：like, uh, um, you know, right?, I mean, sort of, kind of 等。
- 修正明显语音识别错误和口误，但不得改变说话人观点。
- 保留专有名词原文或中文通用译名（如 Bitcoin→比特币，Ethereum→以太坊）。
- 使用中文全角标点。
- 广告、赞助、订阅呼吁片段跳过，不出现在正文中。
- 单字确认回应如 "Yeah."、"Right."、"嗯。"、"对。" 合并到上下文中，不单独成段。

完整性与反幻觉：
- 每一句正文都必须能在原始逐字稿或 source_metadata 中找到来源。
- 不得凭记忆、推断或感觉补充内容。
- 不得用概括代替正文整理；每个实质性观点、例子、推理都要保留。
- 不得以篇幅为由跳过内容。
- 如果 speaker_name_map 只有 speaker1、speaker2 等泛化标签，保持这些 fallback 标签，不要编造真实姓名。
- 不要输出代码围栏（```）、JSON 或解释性文字。
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
        *_site_options(url),
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
        "You are the podcast-notes skill inside VoiceScribe WebUI. The following skill rules are authoritative "
        "and must be followed exactly. Use only the transcript as source. Do not invent facts, quotes, speaker identities, "
        "sponsors, dates, or links. If metadata is missing, write 未填写. Use the provided speaker_name_map exactly. "
        "If a speaker maps to speaker1, speaker2, etc., keep that fallback label and do not invent a real name. "
        "Match the examples/output/*.md TechFlow article style as closely as possible.\n\n"
        f"{PODCAST_NOTES_SKILL_RULES}"
    )
    output_contract = [
        "Start with the metadata block: 整理 & 编译：深潮TechFlow, optional 嘉宾, 主持人, 播客源, 原标题, 播出日期.",
        "Do not add a fixed [图片] line. Omit 嘉宾 line when there is no guest.",
        "Write 要点总结 as one paragraph of 3-5 Chinese sentences, not bullets.",
        "Write 精彩观点摘要 as chapter groups: （chapter title） followed by * \"quote\" ——speaker bullets.",
        "Write the full dialogue body after 精彩观点摘要, sectioned exactly by chapter_items order.",
        "Body section titles are plain lines, not ## headings, not bullets, and not bold.",
        "Host lines must be '主持人 Name：content' on one line. Guest/non-host lines must be 'Name：' on one line, then content on the next line.",
        "No blank lines between dialogue paragraphs inside the body.",
        "End with 原文链接：[URL] or 原文链接：暂无.",
    ]

    user_prompt = {
        "metadata": metadata,
        "chapter_outline": chapters,
        "chapter_items": chapter_items,
        "speaker_name_map": speaker_name_map,
        "source_metadata": source_metadata,
        "output_contract": output_contract,
        "speaker_notes": [
            "If host/guest names include mappings such as SPEAKER_00=姓名 or Speaker 1=Alice, apply them strictly.",
            "If the speaker_name_map has only speaker1, speaker2 generic labels, use them as-is without inventing real names.",
            "The first speaker in the transcript is typically the host unless host metadata says otherwise.",
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
