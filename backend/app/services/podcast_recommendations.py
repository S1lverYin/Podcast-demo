import csv
import json
import math
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from app.config import get_settings
from app.services.downloader import _site_options, validate_public_http_url, yt_dlp_command
from app.services.podcast_notes import (
    _anthropic_completion,
    _api_config,
    _clean_text,
    _extract_json_payload,
    _openai_compatible_completion,
)


@dataclass
class SeedItem:
    title: str
    url: str
    source: str | None
    description: str | None


@dataclass
class PodcastRecommendation:
    title: str
    url: str
    source: str | None
    published_date: str | None
    duration: int | None
    reason: str
    query: str | None = None


@dataclass
class SubscriptionChannel:
    channel_id: str
    url: str
    title: str


STOPWORDS = {
    "about",
    "after",
    "and",
    "are",
    "because",
    "before",
    "but",
    "for",
    "from",
    "how",
    "into",
    "podcast",
    "that",
    "the",
    "this",
    "video",
    "what",
    "when",
    "where",
    "which",
    "with",
    "will",
    "you",
    "your",
}


DEFAULT_SUBSCRIPTION_CSV = Path(__file__).resolve().parents[1] / "data" / "subscriptions.csv"


def _run_ytdlp_json(target: str, *, timeout: int = 90, site_url: str | None = None) -> dict[str, Any]:
    command = [
        *yt_dlp_command(),
        "--dump-single-json",
        "--skip-download",
        "--no-warnings",
        "--no-playlist",
    ]
    if site_url:
        command.extend(_site_options(site_url))
    command.append(target)
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Could not fetch metadata")
    return json.loads(result.stdout)


def _run_ytdlp_playlist_json(target: str, *, timeout: int = 120, playlist_end: int = 8) -> dict[str, Any]:
    command = [
        *yt_dlp_command(),
        "--dump-single-json",
        "--skip-download",
        "--no-warnings",
        "--playlist-end",
        str(playlist_end),
        target,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Could not fetch channel metadata")
    return json.loads(result.stdout)


def _entry_url(entry: dict[str, Any]) -> str:
    url = _clean_text(entry.get("webpage_url") or entry.get("original_url") or entry.get("url"))
    if url.startswith("http"):
        return url
    video_id = _clean_text(entry.get("id"))
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else ""


def _parse_upload_datetime(entry: dict[str, Any]) -> datetime | None:
    raw_date = _clean_text(entry.get("release_date") or entry.get("upload_date"))
    if re.fullmatch(r"\d{8}", raw_date):
        return datetime(
            int(raw_date[:4]),
            int(raw_date[4:6]),
            int(raw_date[6:8]),
            tzinfo=timezone.utc,
        )
    timestamp = entry.get("timestamp")
    if isinstance(timestamp, (int, float)):
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return None


def _format_published_date(entry: dict[str, Any]) -> str | None:
    published_at = _parse_upload_datetime(entry)
    if not published_at:
        return None
    return f"{published_at.year}年{published_at.month}月{published_at.day}日"


def _fetch_seed_metadata(url: str) -> SeedItem | None:
    clean_url = _clean_text(url)
    if not clean_url:
        return None
    validate_public_http_url(clean_url)
    try:
        raw = _run_ytdlp_json(clean_url, timeout=90, site_url=clean_url)
    except Exception:
        return None
    title = _clean_text(raw.get("title") or raw.get("fulltitle"))
    resolved_url = _entry_url(raw) or clean_url
    source = _clean_text(raw.get("channel") or raw.get("uploader") or raw.get("creator") or raw.get("series")) or None
    description = _clean_text(raw.get("description"))[:1400] or None
    if not title:
        return None
    return SeedItem(title=title, url=resolved_url, source=source, description=description)


def _terms(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
    return {word for word in words if word not in STOPWORDS and len(word) <= 40}


def _term_counts(text: str) -> Counter[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
    return Counter(word for word in words if word not in STOPWORDS and len(word) <= 40)


def _cosine_similarity(left: Counter[str], right: Counter[str], idf: dict[str, float]) -> float:
    shared = set(left) & set(right)
    numerator = sum(left[token] * right[token] * idf.get(token, 1.0) ** 2 for token in shared)
    left_norm = math.sqrt(sum((count * idf.get(token, 1.0)) ** 2 for token, count in left.items()))
    right_norm = math.sqrt(sum((count * idf.get(token, 1.0)) ** 2 for token, count in right.items()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _candidate_text(entry: dict[str, Any]) -> str:
    return " ".join(
        [
            _clean_text(entry.get("title") or entry.get("fulltitle")),
            _clean_text(entry.get("description"))[:1200],
            _clean_text(entry.get("channel") or entry.get("uploader") or entry.get("creator")),
        ]
    )


def _subscription_csv_path() -> Path:
    configured = _clean_text(get_settings().podcast_subscription_csv)
    if configured:
        path = Path(configured).expanduser()
        if path.is_absolute():
            return path
        cwd_path = path.resolve()
        if cwd_path.exists():
            return cwd_path
    return DEFAULT_SUBSCRIPTION_CSV


@lru_cache(maxsize=1)
def _load_subscription_channels() -> tuple[SubscriptionChannel, ...]:
    path = _subscription_csv_path()
    if not path.exists():
        return ()

    channels: list[SubscriptionChannel] = []
    seen_urls: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            url = _clean_text(row.get("频道网址") or row.get("channel_url") or row.get("url"))
            title = _clean_text(row.get("频道标题") or row.get("channel_title") or row.get("title"))
            channel_id = _clean_text(row.get("频道 ID") or row.get("channel_id") or row.get("id"))
            if not url.startswith("http") or not title or url in seen_urls:
                continue
            channels.append(SubscriptionChannel(channel_id=channel_id, url=url, title=title))
            seen_urls.add(url)
    return tuple(channels)


def list_subscription_channels() -> list[SubscriptionChannel]:
    """Return channels from the local subscription CSV."""
    return list(_load_subscription_channels())


def _derive_channel_id(url: str) -> str:
    cleaned = url.rstrip("/")
    tail = cleaned.rsplit("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9_.@-]+", "-", tail).strip("-")[:80] or cleaned[:80]


def _write_subscription_channels(channels: list[SubscriptionChannel]) -> None:
    path = _subscription_csv_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["频道 ID", "频道网址", "频道标题"])
        writer.writeheader()
        for channel in channels:
            writer.writerow(
                {
                    "频道 ID": channel.channel_id,
                    "频道网址": channel.url,
                    "频道标题": channel.title,
                }
            )
    _load_subscription_channels.cache_clear()


def add_subscription_channel(channel_id: str | None, url: str, title: str) -> SubscriptionChannel:
    clean_url = _clean_text(url)
    clean_title = _clean_text(title)
    clean_id = _clean_text(channel_id) or _derive_channel_id(clean_url)
    if not clean_url.startswith("http"):
        raise ValueError("Subscription URL must be a public HTTP URL")
    validate_public_http_url(clean_url)
    if not clean_title:
        raise ValueError("Subscription title is required")

    channels = list_subscription_channels()
    normalized_url = clean_url.rstrip("/")
    normalized_id = clean_id.lower()
    for channel in channels:
        if channel.url.rstrip("/") == normalized_url or channel.channel_id.lower() == normalized_id:
            raise ValueError("Subscription channel already exists")

    channel = SubscriptionChannel(channel_id=clean_id, url=clean_url, title=clean_title)
    channels.append(channel)
    channels.sort(key=lambda item: item.title.lower())
    _write_subscription_channels(channels)
    return channel


def delete_subscription_channel(channel_id: str) -> None:
    clean_id = _clean_text(channel_id)
    channels = list_subscription_channels()
    kept = [channel for channel in channels if channel.channel_id != clean_id]
    if len(kept) == len(channels):
        raise ValueError("Subscription channel not found")
    _write_subscription_channels(kept)


def _select_subscription_channels(seed_items: list[SeedItem], limit: int) -> list[SubscriptionChannel]:
    channels = list(_load_subscription_channels())
    if not channels:
        return []
    seed_text = " ".join([item.title for item in seed_items] + [item.description or "" for item in seed_items])
    seed_counts = _term_counts(seed_text)
    if not seed_counts:
        return channels[:limit]

    channel_counts = {
        channel.url: _term_counts(f"{channel.title} {channel.channel_id} {channel.url}")
        for channel in channels
    }
    documents = [set(seed_counts), *(set(counts) for counts in channel_counts.values())]
    document_frequency: Counter[str] = Counter()
    for document in documents:
        document_frequency.update(document)
    total = max(1, len(documents))
    idf = {token: math.log((1 + total) / (1 + frequency)) + 1 for token, frequency in document_frequency.items()}
    ranked = sorted(
        channels,
        key=lambda channel: _cosine_similarity(seed_counts, channel_counts[channel.url], idf),
        reverse=True,
    )
    scored = [
        channel
        for channel in ranked
        if _cosine_similarity(seed_counts, channel_counts[channel.url], idf) > 0
    ]
    return (scored or ranked)[:limit]


def _channel_videos_url(channel: SubscriptionChannel) -> str:
    clean_url = channel.url.rstrip("/")
    return clean_url if clean_url.endswith("/videos") else f"{clean_url}/videos"


def _fetch_subscription_channel_entries(
    channel: SubscriptionChannel,
    *,
    days: int,
    limit: int,
) -> list[dict[str, Any]]:
    try:
        raw = _run_ytdlp_playlist_json(_channel_videos_url(channel), playlist_end=limit, timeout=120)
    except Exception:
        return []
    entries = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    found: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        url = _entry_url(entry)
        title = _clean_text(entry.get("title") or entry.get("fulltitle"))
        if not url or not title:
            continue
        published_at = _parse_upload_datetime(entry)
        is_recent = bool(published_at and published_at >= cutoff)
        if published_at and not is_recent:
            continue
        entry["_recommendation_url"] = url
        entry["_recommendation_query"] = f"订阅列表：{channel.title}"
        entry["_recommendation_is_recent"] = is_recent
        entry["_recommendation_stage"] = "subscription"
        entry["_recommendation_subscription_source"] = True
        entry["_recommendation_subscription_channel"] = channel.title
        if not _clean_text(entry.get("channel") or entry.get("uploader") or entry.get("creator")):
            entry["channel"] = channel.title
        found.append(entry)
    return found


def _search_subscription_channels(
    seed_items: list[SeedItem],
    *,
    days: int,
    max_results: int,
) -> list[dict[str, Any]]:
    channel_limit = min(8, max(4, max_results + 3))
    video_limit = min(8, max(4, max_results))
    entries: list[dict[str, Any]] = []
    for channel in _select_subscription_channels(seed_items, channel_limit):
        entries.extend(_fetch_subscription_channel_entries(channel, days=days, limit=video_limit))
    return entries


def _fallback_queries(seed_items: list[SeedItem]) -> list[str]:
    queries: list[str] = []
    for item in seed_items:
        base = re.sub(r"\s+", " ", re.sub(r"[^\w\u4e00-\u9fff+#.\- ]+", " ", item.title)).strip()
        if base:
            queries.append(base[:90])
        if item.source:
            queries.append(f"{item.source} podcast interview")
    seed_text = " ".join([item.title for item in seed_items] + [item.description or "" for item in seed_items])
    top_terms = sorted(_terms(seed_text), key=lambda term: (-seed_text.lower().count(term), term))[:8]
    if top_terms:
        queries.append(" ".join(top_terms[:5]))
    unique: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = query.lower()
        if normalized and normalized not in seen:
            unique.append(query)
            seen.add(normalized)
    return unique[:4] or ["podcast interview"]


def _fallback_keyword_queries(keywords: str) -> list[str]:
    cleaned = _clean_text(keywords)
    if not cleaned:
        return []
    variants = [
        cleaned,
        f"{cleaned} podcast",
        f"{cleaned} interview",
        f"{cleaned} discussion",
    ]
    unique: list[str] = []
    seen: set[str] = set()
    for query in variants:
        normalized = query.lower()
        if normalized not in seen:
            unique.append(query[:100])
            seen.add(normalized)
    return unique[:4]


def _llm_keyword_queries(keywords: str) -> list[str]:
    cleaned = _clean_text(keywords)
    if not cleaned:
        return []
    fallback = _fallback_keyword_queries(cleaned)
    try:
        provider, base_url, api_key, model = _api_config()
    except Exception:
        return fallback

    system_prompt = (
        "You expand user keywords into concise YouTube/podcast search queries. "
        "Return JSON only: {\"queries\": [\"...\"]}. Use 3-5 queries. "
        "Keep important people, companies, products, and topic terms."
    )
    user_prompt = {"keywords": cleaned}
    try:
        content = (
            _anthropic_completion(base_url, api_key, model, system_prompt, user_prompt)
            if provider == "anthropic"
            else _openai_compatible_completion(base_url, api_key, model, system_prompt, user_prompt)
        )
        payload = _extract_json_payload(content)
        raw_queries = payload.get("queries", []) if isinstance(payload, dict) else []
        queries = [_clean_text(query)[:100] for query in raw_queries if _clean_text(query)]
        return queries[:5] or fallback
    except Exception:
        return fallback


def _llm_queries(seed_items: list[SeedItem]) -> list[str]:
    try:
        provider, base_url, api_key, model = _api_config()
    except Exception:
        return _fallback_queries(seed_items)

    system_prompt = (
        "You generate concise YouTube/podcast search queries from seed video metadata. "
        "Return JSON only: {\"queries\": [\"...\"]}. Use 3-5 queries. "
        "Prefer stable topics, people, companies, and domains; avoid copying full long titles."
    )
    user_prompt = {
        "seed_items": [
            {
                "title": item.title,
                "source": item.source,
                "description": item.description,
                "url": item.url,
            }
            for item in seed_items
        ],
    }
    try:
        content = (
            _anthropic_completion(base_url, api_key, model, system_prompt, user_prompt)
            if provider == "anthropic"
            else _openai_compatible_completion(base_url, api_key, model, system_prompt, user_prompt)
        )
        payload = _extract_json_payload(content)
        raw_queries = payload.get("queries", []) if isinstance(payload, dict) else []
        queries = [_clean_text(query)[:100] for query in raw_queries if _clean_text(query)]
        return queries[:5] or _fallback_queries(seed_items)
    except Exception:
        return _fallback_queries(seed_items)


def _search_youtube(
    query: str,
    *,
    days: int,
    limit: int = 12,
    sort_by_date: bool = True,
    strict_recent: bool = True,
) -> list[dict[str, Any]]:
    target = f"ytsearchdate{limit}:{query}" if sort_by_date else f"ytsearch{limit}:{query}"
    try:
        raw = _run_ytdlp_json(target, timeout=120)
    except Exception:
        return []
    entries = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent_entries: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        published_at = _parse_upload_datetime(entry)
        is_recent = bool(published_at and published_at >= cutoff)
        if strict_recent and not is_recent:
            continue
        url = _entry_url(entry)
        title = _clean_text(entry.get("title") or entry.get("fulltitle"))
        if url and title:
            entry["_recommendation_url"] = url
            entry["_recommendation_query"] = query
            entry["_recommendation_is_recent"] = is_recent
            entry["_recommendation_stage"] = "recent" if is_recent else "expanded"
            recent_entries.append(entry)
    return recent_entries


def _score_candidate(seed_counts: Counter[str], entry: dict[str, Any], idf: dict[str, float]) -> float:
    candidate_counts = _term_counts(_candidate_text(entry))
    similarity = _cosine_similarity(seed_counts, candidate_counts, idf)
    duration = entry.get("duration")
    duration_bonus = 1.0 if isinstance(duration, (int, float)) and duration >= 600 else 0.0
    published_at = _parse_upload_datetime(entry)
    recency_bonus = 0.0
    if published_at:
        age_hours = max(0.0, (datetime.now(timezone.utc) - published_at).total_seconds() / 3600)
        recency_bonus = max(0.0, 1.5 - math.log1p(age_hours) / 4)
    strict_recent_bonus = 1.25 if entry.get("_recommendation_is_recent") else 0.0
    subscription_bonus = 1.75 if entry.get("_recommendation_subscription_source") else 0.0
    return similarity * 12.0 + duration_bonus + recency_bonus + strict_recent_bonus + subscription_bonus


def _build_idf(seed_counts: Counter[str], entries: list[dict[str, Any]]) -> dict[str, float]:
    documents = [set(seed_counts)]
    documents.extend(set(_term_counts(_candidate_text(entry))) for entry in entries)
    total = max(1, len(documents))
    document_frequency: Counter[str] = Counter()
    for document in documents:
        document_frequency.update(document)
    return {token: math.log((1 + total) / (1 + frequency)) + 1 for token, frequency in document_frequency.items()}


def _build_fallback_recommendations(
    seed_items: list[SeedItem],
    entries: list[dict[str, Any]],
    max_results: int,
) -> list[PodcastRecommendation]:
    seed_counts = _term_counts(" ".join([item.title for item in seed_items] + [item.description or "" for item in seed_items]))
    idf = _build_idf(seed_counts, entries)
    ranked = sorted(entries, key=lambda entry: _score_candidate(seed_counts, entry, idf), reverse=True)
    recommendations: list[PodcastRecommendation] = []
    for entry in ranked[:max_results]:
        freshness = "7 天内发布" if entry.get("_recommendation_is_recent") else "扩展时间范围后找到"
        if entry.get("_recommendation_subscription_source"):
            channel = _clean_text(entry.get("_recommendation_subscription_channel")) or "订阅频道"
            reason = f"订阅列表频道「{channel}」的近期更新，按主题相似度命中。"
        else:
            reason = f"TF-IDF 相似度排序命中，{freshness}。"
        recommendations.append(
            PodcastRecommendation(
                title=_clean_text(entry.get("title") or entry.get("fulltitle")),
                url=entry["_recommendation_url"],
                source=_clean_text(entry.get("channel") or entry.get("uploader") or entry.get("creator")) or None,
                published_date=_format_published_date(entry),
                duration=int(entry["duration"]) if isinstance(entry.get("duration"), (int, float)) else None,
                reason=reason,
                query=entry.get("_recommendation_query"),
            )
        )
    return recommendations


def _llm_rerank(
    seed_items: list[SeedItem],
    entries: list[dict[str, Any]],
    max_results: int,
) -> list[PodcastRecommendation] | None:
    try:
        provider, base_url, api_key, model = _api_config()
    except Exception:
        return None
    candidate_payload = [
        {
            "title": _clean_text(entry.get("title") or entry.get("fulltitle")),
            "url": entry["_recommendation_url"],
            "source": _clean_text(entry.get("channel") or entry.get("uploader") or entry.get("creator")),
            "published_date": _format_published_date(entry),
            "duration": entry.get("duration"),
            "query": entry.get("_recommendation_query"),
            "is_recent": bool(entry.get("_recommendation_is_recent")),
            "stage": entry.get("_recommendation_stage"),
            "source_type": "subscription_list" if entry.get("_recommendation_subscription_source") else "youtube_search",
        }
        for entry in entries[:30]
    ]
    system_prompt = (
        "You select similar recent podcast/video recommendations. "
        "Use only the provided candidates. Return JSON only: "
        "{\"items\":[{\"url\":\"...\",\"reason\":\"中文推荐理由，不超过45字\"}]}. "
        "Pick diverse but strongly similar items. Prioritize is_recent=true candidates. "
        "If there are not enough recent candidates, expanded candidates are acceptable."
    )
    user_prompt = {
        "seed_items": [
            {
                "title": item.title,
                "source": item.source,
                "description": item.description,
            }
            for item in seed_items
        ],
        "candidates": candidate_payload,
        "max_results": max_results,
    }
    try:
        content = (
            _anthropic_completion(base_url, api_key, model, system_prompt, user_prompt)
            if provider == "anthropic"
            else _openai_compatible_completion(base_url, api_key, model, system_prompt, user_prompt)
        )
        payload = _extract_json_payload(content)
        raw_items = payload.get("items", []) if isinstance(payload, dict) else []
    except Exception:
        return None

    by_url = {entry["_recommendation_url"]: entry for entry in entries}
    selected: list[PodcastRecommendation] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        url = _clean_text(item.get("url"))
        entry = by_url.get(url)
        if not entry or url in seen:
            continue
        seen.add(url)
        selected.append(
            PodcastRecommendation(
                title=_clean_text(entry.get("title") or entry.get("fulltitle")),
                url=url,
                source=_clean_text(entry.get("channel") or entry.get("uploader") or entry.get("creator")) or None,
                published_date=_format_published_date(entry),
                duration=int(entry["duration"]) if isinstance(entry.get("duration"), (int, float)) else None,
                reason=_clean_text(item.get("reason")) or "主题相似且发布时间较新。",
                query=entry.get("_recommendation_query"),
            )
        )
        if len(selected) >= max_results:
            break
    return selected or None


def _build_search_fallback_recommendations(
    queries: list[str],
    max_results: int,
    days: int,
) -> list[PodcastRecommendation]:
    query_pool: list[str] = []
    source_queries = queries or ["podcast interview"]
    for query in source_queries:
        cleaned = _clean_text(query)
        if not cleaned:
            continue
        query_pool.extend(
            [
                cleaned,
                f"{cleaned} podcast",
                f"{cleaned} interview",
                f"{cleaned} latest",
                f"{cleaned} discussion",
            ]
        )

    recommendations: list[PodcastRecommendation] = []
    seen: set[str] = set()
    for query in query_pool:
        normalized = query.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        recommendations.append(
            PodcastRecommendation(
                title=f"继续搜索：{query}",
                url=url,
                source="YouTube 搜索",
                published_date=f"近 {days} 天优先",
                duration=None,
                reason="没有抓到足够具体条目时的兜底入口，保证本次推荐有可打开输出。",
                query=query,
            )
        )
        if len(recommendations) >= max_results:
            break

    while len(recommendations) < max_results:
        index = len(recommendations) + 1
        query = f"podcast recommendation {index}"
        recommendations.append(
            PodcastRecommendation(
                title=f"继续搜索：{query}",
                url=f"https://www.youtube.com/results?search_query={quote_plus(query)}",
                source="YouTube 搜索",
                published_date=f"近 {days} 天优先",
                duration=None,
                reason="兜底搜索入口，保证推荐区域始终有输出。",
                query=query,
            )
        )
    return recommendations[:max_results]


def _fallback_curation_report(items: list[dict[str, Any]], target_audience: str | None = None) -> str:
    audience = _clean_text(target_audience) or "深潮读者"
    strong = items[:1]
    workable = items[1:4]
    average = items[4:]
    lines = [
        "## 今日总览",
        "",
        f"- 面向读者：{audience}",
        f"- 强推：{len(strong)} 条",
        f"- 可做：{len(workable)} 条",
        f"- 一般：{len(average)} 条",
        "- 判断方式：根据推荐理由、来源、时效和主题相关性做本地排序；未接入 LLM 时不编造嘉宾身份。",
        "",
        "## 内容清单",
        "",
    ]
    buckets = [("⭐⭐⭐", strong), ("⭐⭐", workable), ("⭐", average)]
    for rating, bucket in buckets:
        for item in bucket:
            title = _clean_text(item.get("title")) or "未命名内容"
            source = _clean_text(item.get("source")) or "无法判断"
            published_date = _clean_text(item.get("published_date")) or "无法判断"
            reason = _clean_text(item.get("reason")) or "主题相关，但缺少更细信息。"
            url = _clean_text(item.get("url")) or ""
            lines.extend(
                [
                    f"### {rating} {title}",
                    "",
                    f"- 频道 / 来源：{source}",
                    f"- 发布时间：{published_date}",
                    "- 嘉宾身份：无法判断",
                    f"- 核心议题：{_clean_text(item.get('query')) or title}",
                    f"- 亮点 / 争议 / 独家性：{reason}",
                    "- 适合形式：短摘要 / 观点切片 / 选题备选",
                    f"- 推荐理由：{reason}",
                    f"- 原始链接：{url}",
                    "",
                ]
            )

    top_title = _clean_text(strong[0].get("title")) if strong else "暂无明确强推"
    lines.extend(
        [
            "## 专题组合建议",
            "",
            "可将同主题的订阅频道更新与外部搜索结果组合成一个“今日加密播客/视频观察”小专题，优先挑选来源明确、发布时间近、议题有分歧的内容。",
            "",
            "## 编辑建议",
            "",
            "先处理强推项；可做项作为补充素材；一般项只适合放入短列表或观察池。",
            "",
            "## 今天只能做一条，做哪条",
            "",
            f"做：{top_title}",
        ]
    )
    return "\n".join(lines)


def generate_curation_report(items: list[dict[str, Any]], target_audience: str | None = None) -> str:
    clean_items = [
        {
            "title": _clean_text(item.get("title")),
            "url": _clean_text(item.get("url")),
            "source": _clean_text(item.get("source")),
            "published_date": _clean_text(item.get("published_date")),
            "reason": _clean_text(item.get("reason")),
            "query": _clean_text(item.get("query")),
        }
        for item in items
        if _clean_text(item.get("title")) and _clean_text(item.get("url"))
    ]
    if not clean_items:
        raise ValueError("At least one recommendation item is required")

    audience = _clean_text(target_audience) or "深潮读者"
    try:
        provider, base_url, api_key, model = _api_config()
    except Exception:
        return _fallback_curation_report(clean_items, audience)

    system_prompt = (
        "你是加密中文媒体的选题编辑。根据给定推荐条目生成一份深潮 TechFlow 风格的内容策展日报。"
        "必须筛选，不要全都强推。输出 Markdown。必须包含：今日总览、内容清单、专题组合建议、编辑建议、今天只能做一条做哪条。"
        "每条内容要给星级、中文标题、嘉宾身份（不知道就写无法判断）、核心议题、亮点/争议/独家性、适合形式、推荐理由、原始链接。"
        "只能使用用户提供的条目字段，不得编造嘉宾、数据、时间、争议、独家信息或视频内容；信息不足时直接写无法判断。"
        "最后一节标题必须严格写成：## 今天只能做一条，做哪条"
    )
    user_prompt = {
        "target_audience": audience,
        "items": clean_items,
    }
    try:
        content = (
            _anthropic_completion(base_url, api_key, model, system_prompt, user_prompt)
            if provider == "anthropic"
            else _openai_compatible_completion(base_url, api_key, model, system_prompt, user_prompt)
        )
        markdown = (content or "").strip()
        return markdown or _fallback_curation_report(clean_items, audience)
    except Exception:
        return _fallback_curation_report(clean_items, audience)


def recommend_recent_podcasts(
    links: list[str],
    *,
    keywords: str | None = None,
    max_results: int = 5,
    days: int = 7,
    search_subscriptions: bool = False,
) -> list[PodcastRecommendation]:
    """Recommend recent YouTube videos or podcasts similar to supplied links or keywords."""
    clean_keywords = _clean_text(keywords)
    link_seed_items = [item for link in links if (item := _fetch_seed_metadata(link))]
    seed_items = list(link_seed_items)
    if clean_keywords:
        seed_items.append(
            SeedItem(
                title=f"关键词：{clean_keywords}",
                url="",
                source="关键词搜索",
                description=clean_keywords,
            )
        )
    if not seed_items and search_subscriptions:
        seed_items.append(
            SeedItem(
                title="订阅列表近期更新",
                url="",
                source="订阅列表",
                description="从订阅频道列表中搜索近期视频和播客更新",
            )
        )
    if not seed_items:
        raise ValueError("Could not fetch metadata from any supplied link and no keyword was provided")

    input_urls = {item.url for item in link_seed_items if item.url}
    entries: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    queries: list[str] = []
    if clean_keywords:
        queries.extend(_llm_keyword_queries(clean_keywords))
    if link_seed_items:
        queries.extend(_llm_queries(link_seed_items))
    if not queries:
        queries = _fallback_queries(seed_items)

    unique_queries: list[str] = []
    seen_queries: set[str] = set()
    for query in queries:
        normalized = query.lower().strip()
        if normalized and normalized not in seen_queries:
            unique_queries.append(query)
            seen_queries.add(normalized)

    def add_entries(found: list[dict[str, Any]]) -> None:
        for entry in found:
            url = entry["_recommendation_url"]
            if url in input_urls or url in seen_urls:
                continue
            seen_urls.add(url)
            entries.append(entry)

    if search_subscriptions:
        add_entries(_search_subscription_channels(seed_items, days=days, max_results=max_results))

    for query in unique_queries[:8]:
        add_entries(_search_youtube(query, days=days, limit=12, sort_by_date=True, strict_recent=True))

    if len(entries) < max_results:
        for query in unique_queries[:6]:
            add_entries(_search_youtube(query, days=days, limit=10, sort_by_date=True, strict_recent=False))

    if len(entries) < max_results:
        for query in unique_queries[:5]:
            add_entries(_search_youtube(query, days=days, limit=10, sort_by_date=False, strict_recent=False))

    if not entries:
        return _build_search_fallback_recommendations(unique_queries, max_results, days)

    seed_counts = _term_counts(" ".join([item.title for item in seed_items] + [item.description or "" for item in seed_items]))
    idf = _build_idf(seed_counts, entries)
    ranked_entries = sorted(entries, key=lambda entry: _score_candidate(seed_counts, entry, idf), reverse=True)

    recommendations = _llm_rerank(seed_items, ranked_entries, max_results) or []
    if len(recommendations) < max_results:
        seen_recommendation_urls = {item.url for item in recommendations}
        for item in _build_fallback_recommendations(seed_items, ranked_entries, max_results):
            if item.url in seen_recommendation_urls:
                continue
            recommendations.append(item)
            seen_recommendation_urls.add(item.url)
            if len(recommendations) >= max_results:
                break

    if len(recommendations) < max_results:
        seen_recommendation_urls = {item.url for item in recommendations}
        for item in _build_search_fallback_recommendations(unique_queries, max_results, days):
            if item.url in seen_recommendation_urls:
                continue
            recommendations.append(item)
            seen_recommendation_urls.add(item.url)
            if len(recommendations) >= max_results:
                break

    return recommendations[:max_results]
