from collections.abc import Callable

from app.schemas import DiarizationSegment, TranscriptSegment


def _overlap_seconds(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def _nearest_speaker(segment: TranscriptSegment, diarization_segments: list[DiarizationSegment]) -> str | None:
    midpoint = (segment.start + segment.end) / 2
    nearest = min(
        diarization_segments,
        key=lambda item: min(abs(midpoint - item.start), abs(midpoint - item.end)),
        default=None,
    )
    return nearest.speaker if nearest else None


def assign_speakers_to_transcript(
    transcript_segments: list[TranscriptSegment],
    diarization_segments: list[DiarizationSegment],
    progress_callback: Callable[[int], None] | None = None,
) -> list[TranscriptSegment]:
    """Assign speakers to ASR segments by maximum time overlap, falling back to nearest speaker."""
    if not diarization_segments:
        return transcript_segments

    total = len(transcript_segments)
    assigned: list[TranscriptSegment] = []
    for i, segment in enumerate(transcript_segments):
        overlaps = [
            (_overlap_seconds(segment.start, segment.end, speaker.start, speaker.end), speaker.speaker)
            for speaker in diarization_segments
        ]
        best_overlap, speaker = max(overlaps, key=lambda item: item[0])
        assigned_speaker = speaker if best_overlap > 0 else _nearest_speaker(segment, diarization_segments)
        assigned.append(segment.model_copy(update={"speaker": assigned_speaker}))
        if progress_callback and i % max(1, total // 20) == 0:
            progress_callback(min(100, round((i + 1) / total * 100)))
    if progress_callback:
        progress_callback(100)
    return assigned
