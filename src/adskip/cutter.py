from __future__ import annotations

import math
import os
from dataclasses import dataclass
from statistics import median
from pathlib import Path

from .detector import DetectionResult
from .ffmpeg import (
    ACCURATE_SEEK_PREROLL,
    FFmpegError,
    FFmpegTools,
    MediaInfo,
    extract_gray_video,
    extract_rgb_video,
    probe,
    run_command,
)
from .video_match import _sample_indices, _split_frames


MIN_AUTO_CUT_SCORE = 0.90
AUDIO_LEADING_GUARD = 0.006
AUDIO_FADE_DURATION = 0.002
# Audio is perceptually less forgiving than video at a hard cut. In safe mode,
# remove the entire audio/video union plus one full frame on both sides. Keep
# that wider interval independent from the visual cut so it cannot remove
# several extra frames of legitimate motion at the seam.
AUDIO_SAFE_EXTRA_FRAMES = 1
VIDEO_LEADING_GUARD_FRAMES = 3
VIDEO_TRAILING_GUARD_FRAMES = 2
MAX_AUDIO_VIDEO_TAIL_DELTA = 0.12
MAX_RESIDUAL_AD_SCORE = 0.92
MAX_EDGE_RESIDUAL_SCORE = 0.94
SEAM_DUPLICATE_MAD = 0.05
SEAM_BASELINE_MAD = 0.25


@dataclass(frozen=True)
class CutPlan:
    mode: str
    start_frame: int
    end_frame_exclusive: int
    video_start: float
    video_end: float
    audio_start: float
    audio_end: float
    expected_duration: float


@dataclass(frozen=True)
class CutResult:
    output: Path
    expected_duration: float
    actual_duration: float
    plan: CutPlan
    validation: "CutValidation"


@dataclass(frozen=True)
class CutValidation:
    passed: bool
    duration_delta: float
    audio_video_delta: float
    residual_ad_score: float
    residual_ad_start_score: float
    residual_ad_end_score: float
    seam_mad: float | None
    seam_baseline_mad: float | None
    seam_duplicate: bool
    failures: tuple[str, ...]

    def to_report(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "duration_delta": round(self.duration_delta, 6),
            "audio_video_delta": round(self.audio_video_delta, 6),
            "residual_ad_score": round(self.residual_ad_score, 6),
            "residual_ad_start_score": round(self.residual_ad_start_score, 6),
            "residual_ad_end_score": round(self.residual_ad_end_score, 6),
            "seam_mad": None if self.seam_mad is None else round(self.seam_mad, 6),
            "seam_baseline_mad": (
                None if self.seam_baseline_mad is None else round(self.seam_baseline_mad, 6)
            ),
            "seam_duplicate": self.seam_duplicate,
            "failures": list(self.failures),
        }


def build_cut_plan(
    detection: DetectionResult,
    mode: str = "audio-safe",
    *,
    video_leading_guard_frames: int = VIDEO_LEADING_GUARD_FRAMES,
    video_trailing_guard_frames: int = VIDEO_TRAILING_GUARD_FRAMES,
    audio_safe_extra_frames: int = AUDIO_SAFE_EXTRA_FRAMES,
) -> CutPlan:
    fps = detection.video_info.fps
    if min(
        video_leading_guard_frames,
        video_trailing_guard_frames,
        audio_safe_extra_frames,
    ) < 0:
        raise ValueError("安全余量帧数不能小于 0。")
    if mode == "audio-safe":
        protected_video_start = max(
            0.0,
            detection.start - video_leading_guard_frames / fps,
        )
        protected_video_end = min(
            detection.video_info.duration,
            detection.end + video_trailing_guard_frames / fps,
        )
        union_start = min(protected_video_start, detection.audio_cut_start)
        union_end = max(protected_video_end, detection.audio_cut_end)
        start_frame = max(
            0,
            math.floor(union_start * fps) - audio_safe_extra_frames,
        )
        end_frame = math.ceil(union_end * fps - 1e-9) + audio_safe_extra_frames
        video_start = start_frame / fps
        video_end = min(detection.video_info.duration, end_frame / fps)

        # Use one shared interval for both tracks. Earlier versions removed a
        # wider audio interval and inserted equivalent silence at the seam;
        # applying the safe union to video as well preserves sync without a
        # perceptible mute.
        audio_start = video_start
        audio_end = video_end
    elif mode == "precise":
        video_start = detection.start
        video_end = detection.end
        start_frame = round(video_start * fps)
        end_frame = round(video_end * fps)
        audio_start = detection.audio_cut_start
        audio_end = detection.audio_cut_end
    else:
        raise ValueError(f"未知剪切模式：{mode}")

    if video_end <= video_start or audio_end <= audio_start:
        raise ValueError("计算得到的剪切区间无效。")
    return CutPlan(
        mode=mode,
        start_frame=start_frame,
        end_frame_exclusive=end_frame,
        video_start=video_start,
        video_end=video_end,
        audio_start=audio_start,
        audio_end=audio_end,
        expected_duration=detection.video_info.duration - (video_end - video_start),
    )


def prepare_ad_reference(
    source: Path,
    tools: FFmpegTools,
    output: Path,
    *,
    start_frame: int,
    end_frame_exclusive: int,
) -> Path:
    source_info = probe(source, tools)
    if not source_info.has_audio or source_info.fps <= 0:
        raise ValueError("广告来源片段必须包含音轨并具有有效帧率。")
    if start_frame < 0 or end_frame_exclusive <= start_frame:
        raise ValueError("广告帧区间无效。")
    if end_frame_exclusive / source_info.fps > source_info.duration + 1 / source_info.fps:
        raise ValueError("广告结束帧超出了来源片段。")
    if output.exists():
        raise ValueError(f"广告基准文件已存在，为防止覆盖已停止：{output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(f"{output.stem}.partial{output.suffix}")
    partial.unlink(missing_ok=True)
    start = start_frame / source_info.fps
    end = end_frame_exclusive / source_info.fps
    filter_graph = (
        f"[0:v:0]trim=start_frame={start_frame}:end_frame={end_frame_exclusive},"
        "setpts=PTS-STARTPTS[v];"
        f"[0:a:0]atrim=start={start:.9f}:end={end:.9f},asetpts=PTS-STARTPTS[a]"
    )
    try:
        run_command(
            [
                str(tools.ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-i",
                str(source),
                "-filter_complex",
                filter_graph,
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "16",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "256k",
                "-movflags",
                "+faststart",
                "-y",
                str(partial),
            ]
        )
        prepared_info = probe(partial, tools)
        expected = (end_frame_exclusive - start_frame) / source_info.fps
        if not prepared_info.has_audio or abs(prepared_info.duration - expected) > 0.15:
            raise FFmpegError("广告基准文件校验失败。")
        os.replace(partial, output)
        return output
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _extract_preview_frame(
    video: Path,
    tools: FFmpegTools,
    timestamp: float,
    output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    input_seek = max(0.0, timestamp - ACCURATE_SEEK_PREROLL)
    precise_seek = timestamp - input_seek
    run_command(
        [
            str(tools.ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{input_seek:.9f}",
            "-i",
            str(video),
            "-ss",
            f"{precise_seek:.9f}",
            "-vf",
            "scale=960:-2:flags=lanczos,format=yuvj420p",
            "-frames:v",
            "1",
            "-c:v",
            "mjpeg",
            "-threads",
            "1",
            "-q:v",
            "2",
            "-strict",
            "unofficial",
            str(output),
        ]
    )
    if not output.is_file() or output.stat().st_size == 0:
        raise FFmpegError(f"边界预览生成失败：{output}")


def create_boundary_previews(
    detection: DetectionResult,
    tools: FFmpegTools,
    output_dir: Path,
    plan: CutPlan | None = None,
) -> list[Path]:
    start = plan.video_start if plan else detection.start
    end = plan.video_end if plan else detection.end
    frame_duration = 1 / detection.video_info.fps
    timestamps = [
        (max(0.0, start - frame_duration), "01-last-kept-before.jpg"),
        (start, "02-first-removed.jpg"),
        (max(start, end - frame_duration), "03-last-removed.jpg"),
        (end, "04-first-kept-after.jpg"),
    ]
    outputs: list[Path] = []
    for timestamp, filename in timestamps:
        path = output_dir / filename
        _extract_preview_frame(
            detection.video_path,
            tools,
            timestamp,
            path,
        )
        outputs.append(path)
    return outputs


def _best_visual_match_score(
    ad_path: Path,
    output: Path,
    tools: FFmpegTools,
    *,
    fps: float,
    join_time: float,
    ad_duration: float,
) -> float:
    width, height = 32, 18
    frame_size = width * height * 3
    ad_frames = _split_frames(
        extract_rgb_video(ad_path, tools, fps=fps, width=width, height=height),
        frame_size,
    )
    window_start = max(0.0, join_time - 1.0)
    output_frames = _split_frames(
        extract_rgb_video(
            output,
            tools,
            fps=fps,
            width=width,
            height=height,
            start=window_start,
            duration=ad_duration + 2.0,
        ),
        frame_size,
    )
    if not ad_frames or len(output_frames) < len(ad_frames):
        raise FFmpegError("无法完成输出广告残留验收：接缝附近画面不足。")
    indices = _sample_indices(len(ad_frames))
    denominator = len(indices) * frame_size * 255
    best_difference: int | None = None
    for offset in range(len(output_frames) - len(ad_frames) + 1):
        difference = sum(
            sum(abs(a - b) for a, b in zip(ad_frames[index], output_frames[offset + index]))
            for index in indices
        )
        if best_difference is None or difference < best_difference:
            best_difference = difference
    assert best_difference is not None
    return 1.0 - best_difference / denominator


def _best_frame_similarity(left_frames: list[memoryview], right_frames: list[memoryview]) -> float:
    if not left_frames or not right_frames:
        return 0.0
    frame_size = len(left_frames[0])
    best = 0.0
    for left in left_frames:
        for right in right_frames:
            difference = sum(abs(a - b) for a, b in zip(left, right))
            best = max(best, 1.0 - difference / (frame_size * 255))
    return best


def _edge_residual_scores(
    ad_path: Path,
    output: Path,
    tools: FFmpegTools,
    *,
    fps: float,
    join_time: float,
) -> tuple[float, float]:
    """Find short ad fragments on either side of the output join."""
    width, height = 64, 36
    frame_size = width * height * 3
    edge_duration = 0.75
    ad_frames = _split_frames(
        extract_rgb_video(ad_path, tools, fps=fps, width=width, height=height),
        frame_size,
    )
    edge_count = max(4, round(edge_duration * fps))
    if len(ad_frames) < edge_count:
        edge_count = len(ad_frames)

    window_start = max(0.0, join_time - edge_duration)
    output_frames = _split_frames(
        extract_rgb_video(
            output,
            tools,
            fps=fps,
            width=width,
            height=height,
            start=window_start,
            duration=edge_duration * 2,
        ),
        frame_size,
    )
    seam_index = round((join_time - window_start) * fps)
    seam_index = max(0, min(len(output_frames), seam_index))
    before_join = output_frames[:seam_index]
    after_join = output_frames[seam_index:]
    return (
        _best_frame_similarity(ad_frames[:edge_count], before_join),
        _best_frame_similarity(ad_frames[-edge_count:], after_join),
    )


def _seam_metrics(
    output: Path,
    tools: FFmpegTools,
    *,
    fps: float,
    join_time: float,
) -> tuple[float | None, float | None, bool]:
    width, height = 160, 90
    frame_size = width * height
    window_start = max(0.0, join_time - 0.5)
    frames = _split_frames(
        extract_gray_video(
            output,
            tools,
            fps=fps,
            width=width,
            height=height,
            start=window_start,
            duration=1.0,
        ),
        frame_size,
    )
    if len(frames) < 4:
        return None, None, False
    motions = [
        sum(abs(a - b) for a, b in zip(frames[index - 1], frames[index])) / frame_size
        for index in range(1, len(frames))
    ]
    seam_index = round((join_time - window_start) * fps)
    seam_index = max(1, min(len(frames) - 1, seam_index))
    seam_mad = motions[seam_index - 1]
    baseline = [
        value
        for index, value in enumerate(motions)
        if abs(index - (seam_index - 1)) > 2
    ]
    seam_baseline = median(baseline) if baseline else None
    duplicate = (
        seam_mad <= SEAM_DUPLICATE_MAD
        and seam_baseline is not None
        and seam_baseline >= SEAM_BASELINE_MAD
    )
    return seam_mad, seam_baseline, duplicate


def validate_output(
    detection: DetectionResult,
    tools: FFmpegTools,
    output: Path,
    plan: CutPlan,
    output_info: MediaInfo,
    *,
    expected_duration: float,
) -> CutValidation:
    duration_delta = abs(output_info.duration - expected_duration)
    audio_video_delta = (
        abs(output_info.duration - output_info.audio_duration)
        if output_info.audio_duration is not None
        else float("inf")
    )
    residual_ad_score = _best_visual_match_score(
        detection.ad_path,
        output,
        tools,
        fps=detection.video_info.fps,
        join_time=plan.video_start,
        ad_duration=detection.ad_info.duration,
    )
    residual_ad_start_score, residual_ad_end_score = _edge_residual_scores(
        detection.ad_path,
        output,
        tools,
        fps=detection.video_info.fps,
        join_time=plan.video_start,
    )
    seam_mad, seam_baseline, seam_duplicate = _seam_metrics(
        output,
        tools,
        fps=detection.video_info.fps,
        join_time=plan.video_start,
    )
    failures: list[str] = []
    if duration_delta > max(0.25, 2 / detection.video_info.fps):
        failures.append(
            f"输出时长偏差 {duration_delta:.3f}s 超过允许范围。"
        )
    if audio_video_delta > MAX_AUDIO_VIDEO_TAIL_DELTA:
        failures.append(
            f"音视频尾差 {audio_video_delta:.3f}s 超过 {MAX_AUDIO_VIDEO_TAIL_DELTA:.2f}s。"
        )
    if residual_ad_score >= MAX_RESIDUAL_AD_SCORE:
        failures.append(
            f"接缝附近仍疑似存在广告画面（相似度 {residual_ad_score:.4f}）。"
        )
    if residual_ad_start_score >= MAX_EDGE_RESIDUAL_SCORE:
        failures.append(
            "接缝前仍疑似存在广告开头画面"
            f"（相似度 {residual_ad_start_score:.4f}）。"
        )
    if residual_ad_end_score >= MAX_EDGE_RESIDUAL_SCORE:
        failures.append(
            "接缝后仍疑似存在广告结尾画面"
            f"（相似度 {residual_ad_end_score:.4f}）。"
        )
    if seam_duplicate:
        failures.append("接缝处检测到疑似重复帧。")
    return CutValidation(
        passed=not failures,
        duration_delta=duration_delta,
        audio_video_delta=audio_video_delta,
        residual_ad_score=residual_ad_score,
        residual_ad_start_score=residual_ad_start_score,
        residual_ad_end_score=residual_ad_end_score,
        seam_mad=seam_mad,
        seam_baseline_mad=seam_baseline,
        seam_duplicate=seam_duplicate,
        failures=tuple(failures),
    )


def cut_video(
    detection: DetectionResult,
    tools: FFmpegTools,
    output: Path,
    *,
    min_score: float = MIN_AUTO_CUT_SCORE,
    mode: str = "audio-safe",
    video_leading_guard_frames: int = VIDEO_LEADING_GUARD_FRAMES,
    video_trailing_guard_frames: int = VIDEO_TRAILING_GUARD_FRAMES,
    audio_safe_extra_frames: int = AUDIO_SAFE_EXTRA_FRAMES,
) -> CutResult:
    if detection.combined_score < min_score:
        raise ValueError(
            f"综合匹配分 {detection.combined_score:.4f} 低于自动剪切门槛 {min_score:.2f}，"
            "已停止以保护原片。"
        )
    if output.exists():
        raise ValueError(f"输出文件已存在，为防止覆盖已停止：{output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(f"{output.stem}.partial{output.suffix}")
    if partial.exists():
        partial.unlink()

    plan = build_cut_plan(
        detection,
        mode,
        video_leading_guard_frames=video_leading_guard_frames,
        video_trailing_guard_frames=video_trailing_guard_frames,
        audio_safe_extra_frames=audio_safe_extra_frames,
    )
    fps = detection.video_info.fps
    video_start = plan.video_start
    video_end = plan.video_end
    audio_start = plan.audio_start
    audio_end = plan.audio_end
    if audio_end <= audio_start:
        raise ValueError("检测到的音频广告区间无效。")
    expected_duration = plan.expected_duration
    leading_guard = 0.0 if mode == "audio-safe" else AUDIO_LEADING_GUARD
    safe_audio_start = max(0.0, audio_start - leading_guard)
    audio_join_time = video_start + (audio_end - video_end)
    if audio_join_time < safe_audio_start:
        raise ValueError("音频校准产生了重叠区间，当前版本无法安全自动剪切。")
    pre_join_padding = audio_join_time - safe_audio_start
    if mode == "audio-safe" and pre_join_padding > 1e-9:
        raise ValueError("音频安全模式不应在接缝处插入静音。")
    fade = min(
        AUDIO_FADE_DURATION,
        safe_audio_start / 2,
        (detection.video_info.duration - audio_end) / 2,
    )
    fade_out_start = max(0.0, safe_audio_start - fade)
    pre_audio_end_filter = (
        f"apad=pad_dur={pre_join_padding:.9f},atrim=end={audio_join_time:.9f}"
        if pre_join_padding > 1e-9
        else f"atrim=end={audio_join_time:.9f}"
    )
    filter_graph = (
        f"[0:v:0]trim=end={video_start:.9f},"
        "setpts=PTS-STARTPTS,settb=AVTB[v0];"
        f"[0:v:0]trim=start={video_end:.9f},"
        "setpts=PTS-STARTPTS,settb=AVTB[v1];"
        f"[0:a:0]atrim=end={safe_audio_start:.9f},asetpts=PTS-STARTPTS,"
        f"afade=t=out:st={fade_out_start:.9f}:d={fade:.9f},"
        f"{pre_audio_end_filter}[a0];"
        f"[0:a:0]atrim=start={audio_end:.9f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={fade:.9f}[a1];"
        "[v0][v1]concat=n=2:v=1:a=0[v];"
        "[a0][a1]concat=n=2:v=0:a=1[a_join];"
        f"[a_join]apad=whole_dur={expected_duration:.9f},"
        f"atrim=end={expected_duration:.9f}[a]"
    )
    try:
        run_command(
            [
                str(tools.ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-reinit_filter",
                "0",
                "-i",
                str(detection.video_path),
                "-filter_complex",
                filter_graph,
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-map_metadata",
                "0",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-fps_mode",
                "vfr",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                "-y",
                str(partial),
            ]
        )
        output_info = probe(partial, tools)
        expected = expected_duration
        tolerance = max(0.25, 2 / fps)
        if not output_info.has_audio:
            raise FFmpegError("输出文件缺少音轨。")
        if abs(output_info.duration - expected) > tolerance:
            raise FFmpegError(
                f"输出时长校验失败：预期约 {expected:.3f}s，实际 {output_info.duration:.3f}s。"
            )
        validation = validate_output(
            detection,
            tools,
            partial,
            plan,
            output_info,
            expected_duration=expected,
        )
        if not validation.passed:
            raise FFmpegError("输出验收失败：" + "；".join(validation.failures))
        os.replace(partial, output)
        return CutResult(
            output=output,
            expected_duration=expected,
            actual_duration=output_info.duration,
            plan=plan,
            validation=validation,
        )
    except Exception:
        partial.unlink(missing_ok=True)
        raise

