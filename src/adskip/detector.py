from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .audio_match import AudioMatch, locate_ad
from .ffmpeg import FFmpegTools, MediaInfo, probe
from .video_match import VideoMatch, verify_video


DEFAULT_SEARCH_START_RATIO = 0.35
DEFAULT_SEARCH_END_RATIO = 0.65


@dataclass(frozen=True)
class DetectionResult:
    ad_path: Path
    video_path: Path
    ad_info: MediaInfo
    video_info: MediaInfo
    audio: AudioMatch
    video: VideoMatch
    audio_start_adjustment: float = 0.0
    audio_end_adjustment: float = 0.0

    @property
    def start_frame(self) -> int:
        return self.video.start_frame

    @property
    def end_frame_exclusive(self) -> int:
        return self.video.end_frame_exclusive

    @property
    def start(self) -> float:
        return self.video.start_time

    @property
    def end(self) -> float:
        return min(self.video_info.duration, self.video.end_time)

    @property
    def combined_score(self) -> float:
        return 0.55 * self.audio.score + 0.45 * self.video.score

    @property
    def audio_cut_start(self) -> float:
        return max(0.0, self.audio.start + self.audio_start_adjustment)

    @property
    def audio_cut_end(self) -> float:
        return min(self.video_info.duration, self.audio.end + self.audio_end_adjustment)

    @property
    def confidence(self) -> str:
        if self.combined_score >= 0.9:
            return "high"
        if self.combined_score >= 0.7:
            return "medium"
        return "low"

    def to_report(self, *, cut_output: Path | None = None) -> dict[str, object]:
        report: dict[str, object] = {
            "schema_version": 4,
            "tool_version": __version__,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ad_sample": str(self.ad_path),
            "video": str(self.video_path),
            "match": {
                "start": round(self.start, 6),
                "end": round(self.end, 6),
                "duration": round(self.end - self.start, 6),
                "start_frame": self.start_frame,
                "end_frame_exclusive": self.end_frame_exclusive,
                "fps": self.video_info.fps,
                "frame_numbers_are_diagnostic": True,
                "cut_coordinate_system": "stream_timestamp_seconds",
                "audio_match_start": round(self.audio.start, 6),
                "audio_match_end": round(self.audio.end, 6),
                "audio_duration": round(self.audio.duration, 6),
                "audio_start_adjustment": round(self.audio_start_adjustment, 6),
                "audio_end_adjustment": round(self.audio_end_adjustment, 6),
                "audio_cut_start": round(self.audio_cut_start, 6),
                "audio_cut_end": round(self.audio_cut_end, 6),
                "audio_start_offset_from_video": round(self.audio_cut_start - self.start, 6),
                "audio_end_offset_from_video": round(self.audio_cut_end - self.end, 6),
                "audio_score": round(self.audio.score, 6),
                "audio_waveform_score": round(self.audio.waveform_score, 6),
                "video_score": round(self.video.score, 6),
                "combined_score": round(self.combined_score, 6),
                "coarse_start": round(self.audio.coarse_start, 3),
                "coarse_score": round(self.audio.coarse_score, 6),
                "search_start": round(self.audio.search_start, 6),
                "search_end": (
                    None if self.audio.search_end is None else round(self.audio.search_end, 6)
                ),
                "confidence": self.confidence,
                "method": "audio_correlation_plus_video_frame_verification",
            },
        }
        if cut_output is None:
            report["notice"] = "检测报告仅供复核；本次运行没有修改或剪切原视频。"
        else:
            report["output"] = str(cut_output)
            report["notice"] = "原视频未被修改；剪切结果已写入新的输出文件。"
        return report


def load_ad_profile(ad_path: Path) -> tuple[float, float, Path | None]:
    profile_path = ad_path.with_suffix(".profile.json")
    if not profile_path.is_file():
        return 0.0, 0.0, None
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    start_adjustment = float(data.get("audio_start_adjustment_seconds", 0.0))
    end_adjustment = float(data.get("audio_end_adjustment_seconds", 0.0))
    if abs(start_adjustment) > 1 or abs(end_adjustment) > 1:
        raise ValueError(f"广告配置中的音频偏移超过安全范围：{profile_path}")
    return start_adjustment, end_adjustment, profile_path


def detect_ad(
    ad_path: Path,
    video_path: Path,
    tools: FFmpegTools,
    *,
    search_start_ratio: float = DEFAULT_SEARCH_START_RATIO,
    search_end_ratio: float = DEFAULT_SEARCH_END_RATIO,
) -> DetectionResult:
    ad_info = probe(ad_path, tools)
    video_info = probe(video_path, tools)
    if not ad_info.has_audio or not video_info.has_audio:
        raise ValueError("广告样本和待检测视频都必须包含音轨。")
    if video_info.fps <= 0:
        raise ValueError("无法确定目标视频帧率。")
    if not 0 <= search_start_ratio < search_end_ratio <= 1:
        raise ValueError("搜索比例必须满足 0 <= 起点 < 终点 <= 1。")

    audio = locate_ad(
        ad_path,
        video_path,
        tools,
        search_start=video_info.duration * search_start_ratio,
        search_end=video_info.duration * search_end_ratio,
    )
    video = verify_video(
        ad_path,
        video_path,
        tools,
        fps=video_info.fps,
        audio_start=audio.start,
        ad_duration=ad_info.duration,
    )
    start_adjustment, end_adjustment, _ = load_ad_profile(ad_path)
    return DetectionResult(
        ad_path=ad_path,
        video_path=video_path,
        ad_info=ad_info,
        video_info=video_info,
        audio=audio,
        video=video,
        audio_start_adjustment=start_adjustment,
        audio_end_adjustment=end_adjustment,
    )

