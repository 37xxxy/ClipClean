from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


ACCURATE_SEEK_PREROLL = 10.0


@dataclass(frozen=True)
class FFmpegTools:
    ffmpeg: Path
    ffprobe: Path


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    fps: float
    width: int | None
    height: int | None
    has_audio: bool
    frame_count: int | None
    audio_duration: float | None = None


def _candidate_directories() -> list[Path]:
    dirs: list[Path] = []
    configured = os.environ.get("FFMPEG_BIN")
    if configured:
        path = Path(configured).expanduser()
        dirs.append(path if path.is_dir() else path.parent)

    home = Path.home()
    dirs.extend(
        [
            Path(sys.executable).resolve().parent,
            Path.cwd(),
            home / "Desktop" / "ffmpeg" / "ffmpeg" / "bin",
            home / "Desktop" / "ffmpeg" / "bin",
            home / "ffmpeg" / "bin",
            Path("C:/ffmpeg/bin"),
        ]
    )
    return dirs


def find_tools() -> FFmpegTools:
    ffmpeg_on_path = shutil.which("ffmpeg")
    ffprobe_on_path = shutil.which("ffprobe")
    if ffmpeg_on_path and ffprobe_on_path:
        return FFmpegTools(Path(ffmpeg_on_path), Path(ffprobe_on_path))

    for directory in _candidate_directories():
        ffmpeg = directory / "ffmpeg.exe"
        ffprobe = directory / "ffprobe.exe"
        if ffmpeg.is_file() and ffprobe.is_file():
            return FFmpegTools(ffmpeg, ffprobe)

    raise FFmpegError(
        "找不到 ffmpeg.exe 和 ffprobe.exe。请将 FFmpeg 加入 PATH，"
        "或把 FFMPEG_BIN 设置为 FFmpeg 的 bin 目录。"
    )


def run_command(command: list[str], *, binary: bool = False) -> bytes | str:
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise FFmpegError(stderr or f"命令执行失败，退出码 {completed.returncode}")
    if binary:
        return completed.stdout
    return completed.stdout.decode("utf-8", errors="replace")


def probe(path: Path, tools: FFmpegTools) -> MediaInfo:
    output = run_command(
        [
            str(tools.ffprobe),
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    data = json.loads(output)
    streams = data.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    has_audio = audio is not None
    if video is None:
        raise FFmpegError(f"文件没有视频流：{path}")
    fps_text = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
    fps = float(Fraction(fps_text)) if fps_text != "0/0" else 0.0
    duration_text = video.get("duration") or data.get("format", {}).get("duration")
    if not duration_text:
        raise FFmpegError(f"无法读取视频时长：{path}")
    frame_count_text = video.get("nb_frames")
    frame_count = (
        int(frame_count_text)
        if frame_count_text and str(frame_count_text).isdigit()
        else None
    )
    audio_duration_text = None
    if audio is not None:
        audio_duration_text = audio.get("duration") or data.get("format", {}).get("duration")
    return MediaInfo(
        duration=float(duration_text),
        fps=fps,
        width=video.get("width"),
        height=video.get("height"),
        has_audio=has_audio,
        frame_count=frame_count,
        audio_duration=(
            float(audio_duration_text) if audio_duration_text else None
        ),
    )


def extract_pcm(
    path: Path,
    tools: FFmpegTools,
    *,
    sample_rate: int,
    start: float | None = None,
    duration: float | None = None,
) -> bytes:
    command = [str(tools.ffmpeg), "-hide_banner", "-loglevel", "error"]
    if start is not None:
        input_seek = max(0.0, start - ACCURATE_SEEK_PREROLL)
        command.extend(["-ss", f"{input_seek:.6f}"])
    command.extend(["-i", str(path)])
    if start is not None:
        command.extend(["-ss", f"{start - input_seek:.6f}"])
    if duration is not None:
        command.extend(["-t", f"{duration:.6f}"])
    command.extend(
        [
            "-map",
            "0:a:0",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "s16le",
            "-",
        ]
    )
    return run_command(command, binary=True)


def extract_gray_video(
    path: Path,
    tools: FFmpegTools,
    *,
    fps: float,
    width: int = 32,
    height: int = 18,
    start: float | None = None,
    duration: float | None = None,
) -> bytes:
    command = [str(tools.ffmpeg), "-hide_banner", "-loglevel", "error"]
    if start is not None:
        input_seek = max(0.0, start - ACCURATE_SEEK_PREROLL)
        command.extend(["-ss", f"{input_seek:.9f}"])
    command.extend(["-i", str(path)])
    if start is not None:
        command.extend(["-ss", f"{start - input_seek:.9f}"])
    if duration is not None:
        command.extend(["-t", f"{duration:.9f}"])
    command.extend(
        [
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            f"fps={fps:.12g},scale={width}:{height}:flags=area,format=gray",
            "-pix_fmt",
            "gray",
            "-f",
            "rawvideo",
            "-",
        ]
    )
    return run_command(command, binary=True)


def extract_rgb_video(
    path: Path,
    tools: FFmpegTools,
    *,
    fps: float,
    width: int = 32,
    height: int = 18,
    start: float | None = None,
    duration: float | None = None,
) -> bytes:
    command = [str(tools.ffmpeg), "-hide_banner", "-loglevel", "error"]
    if start is not None:
        input_seek = max(0.0, start - ACCURATE_SEEK_PREROLL)
        command.extend(["-ss", f"{input_seek:.9f}"])
    command.extend(["-i", str(path)])
    if start is not None:
        command.extend(["-ss", f"{start - input_seek:.9f}"])
    if duration is not None:
        command.extend(["-t", f"{duration:.9f}"])
    command.extend(
        [
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            f"fps={fps:.12g},scale={width}:{height}:flags=area,format=rgb24",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "-",
        ]
    )
    return run_command(command, binary=True)

