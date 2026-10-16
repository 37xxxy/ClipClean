from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ffmpeg import FFmpegTools, extract_gray_video


@dataclass(frozen=True)
class VideoMatch:
    start_time: float
    end_time: float
    detection_fps: float
    score: float

    @property
    def start_frame(self) -> int:
        """Diagnostic frame number in the CFR detection stream."""
        return round(self.start_time * self.detection_fps)

    @property
    def end_frame_exclusive(self) -> int:
        """Diagnostic frame number in the CFR detection stream."""
        return round(self.end_time * self.detection_fps)


def _split_frames(raw: bytes, frame_size: int) -> list[memoryview]:
    count = len(raw) // frame_size
    view = memoryview(raw)
    return [view[index * frame_size : (index + 1) * frame_size] for index in range(count)]


def _sample_indices(frame_count: int, count: int = 32) -> list[int]:
    if frame_count <= count:
        return list(range(frame_count))
    first = max(0, round((frame_count - 1) * 0.05))
    last = min(frame_count - 1, round((frame_count - 1) * 0.95))
    return sorted({round(first + index * (last - first) / (count - 1)) for index in range(count)})


def verify_video(
    ad_path: Path,
    video_path: Path,
    tools: FFmpegTools,
    *,
    fps: float,
    audio_start: float,
    ad_duration: float,
) -> VideoMatch:
    width, height = 32, 18
    frame_size = width * height
    ad_raw = extract_gray_video(ad_path, tools, fps=fps, width=width, height=height)
    ad_frames = _split_frames(ad_raw, frame_size)
    if not ad_frames:
        raise ValueError("无法从广告样本读取画面帧。")

    radius_frames = max(8, round(fps * 0.75))
    expected_frame = round(audio_start * fps)
    search_start_frame = max(0, expected_frame - radius_frames)
    search_start = search_start_frame / fps
    search_duration = ad_duration + 2 * radius_frames / fps
    video_raw = extract_gray_video(
        video_path,
        tools,
        fps=fps,
        width=width,
        height=height,
        start=search_start,
        duration=search_duration,
    )
    video_frames = _split_frames(video_raw, frame_size)
    if len(video_frames) < len(ad_frames):
        raise ValueError("候选位置附近没有足够画面用于验证广告。")

    indices = _sample_indices(len(ad_frames))
    comparisons = len(indices) * frame_size
    best_offset = 0
    best_difference: int | None = None
    for offset in range(len(video_frames) - len(ad_frames) + 1):
        difference = 0
        for ad_index in indices:
            ad_frame = ad_frames[ad_index]
            video_frame = video_frames[offset + ad_index]
            difference += sum(abs(a - b) for a, b in zip(ad_frame, video_frame))
        if best_difference is None or difference < best_difference:
            best_difference = difference
            best_offset = offset

    assert best_difference is not None
    start_time = search_start + best_offset / fps
    score = 1.0 - best_difference / (comparisons * 255)
    return VideoMatch(
        start_time=start_time,
        end_time=start_time + len(ad_frames) / fps,
        detection_fps=fps,
        score=score,
    )
