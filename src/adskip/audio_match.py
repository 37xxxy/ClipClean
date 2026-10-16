from __future__ import annotations

import math
import sys
from array import array
from dataclasses import dataclass
from pathlib import Path

from .ffmpeg import FFmpegTools, extract_pcm


@dataclass(frozen=True)
class AudioMatch:
    start: float
    duration: float
    score: float
    waveform_score: float
    coarse_start: float
    coarse_score: float
    search_start: float = 0.0
    search_end: float | None = None

    @property
    def end(self) -> float:
        return self.start + self.duration


def _samples(pcm: bytes) -> array:
    values = array("h")
    values.frombytes(pcm)
    if sys.byteorder != "little":
        values.byteswap()
    return values


def _rms_frames(values: array, frame_size: int) -> list[float]:
    result: list[float] = []
    usable = len(values) - (len(values) % frame_size)
    for offset in range(0, usable, frame_size):
        total = 0.0
        for value in values[offset : offset + frame_size]:
            total += value * value
        result.append(math.log1p(math.sqrt(total / frame_size)))
    return result


def _rolling_rms(values: array, window_size: int, hop_size: int) -> list[float]:
    if len(values) < window_size:
        return []
    prefix = [0]
    running = 0
    for value in values:
        running += value * value
        prefix.append(running)
    result: list[float] = []
    for offset in range(0, len(values) - window_size + 1, hop_size):
        total = prefix[offset + window_size] - prefix[offset]
        result.append(math.log1p(math.sqrt(total / window_size)))
    return result


def _center(values: list[float]) -> tuple[list[float], float]:
    mean = sum(values) / len(values)
    centered = [value - mean for value in values]
    energy = math.sqrt(sum(value * value for value in centered))
    return centered, energy


def _correlation_at(
    needle_centered: list[float], needle_energy: float, haystack: list[float], offset: int
) -> float:
    window = haystack[offset : offset + len(needle_centered)]
    mean = sum(window) / len(window)
    dot = 0.0
    energy = 0.0
    for expected, actual in zip(needle_centered, window):
        centered = actual - mean
        dot += expected * centered
        energy += centered * centered
    denominator = needle_energy * math.sqrt(energy)
    return dot / denominator if denominator else -1.0


def _best_offsets(needle: list[float], haystack: list[float], count: int = 4) -> list[tuple[int, float]]:
    if len(haystack) < len(needle):
        raise ValueError("待检测视频比广告样本短，无法完成匹配。")
    centered, energy = _center(needle)
    scored = [
        (offset, _correlation_at(centered, energy, haystack, offset))
        for offset in range(len(haystack) - len(needle) + 1)
    ]
    scored.sort(key=lambda item: item[1], reverse=True)

    selected: list[tuple[int, float]] = []
    exclusion = max(1, len(needle) // 3)
    for candidate in scored:
        if all(abs(candidate[0] - prior[0]) >= exclusion for prior in selected):
            selected.append(candidate)
        if len(selected) == count:
            break
    return selected


def _refine_waveform_offset(
    needle: array,
    haystack: array,
    approximate_offset: int,
    *,
    sample_rate: int,
) -> tuple[int, float]:
    trim = min(sample_rate // 4, max(0, len(needle) // 10))
    first = trim
    last = len(needle) - trim
    step = 8
    needle_values = needle[first:last:step]
    needle_mean = sum(needle_values) / len(needle_values)
    needle_energy = sum((value - needle_mean) ** 2 for value in needle_values)

    best_offset = approximate_offset
    best_score = -1.0
    radius = max(16, sample_rate // 250)
    for candidate in range(approximate_offset - radius, approximate_offset + radius + 1):
        start = candidate + first
        end = candidate + last
        if start < 0 or end > len(haystack):
            continue
        window = haystack[start:end:step]
        window_mean = sum(window) / len(window)
        dot = 0.0
        window_energy = 0.0
        for expected, actual in zip(needle_values, window):
            left = expected - needle_mean
            right = actual - window_mean
            dot += left * right
            window_energy += right * right
        denominator = math.sqrt(needle_energy * window_energy)
        score = dot / denominator if denominator else -1.0
        if score > best_score:
            best_offset = candidate
            best_score = score
    return best_offset, best_score


def locate_ad(
    ad_path: Path,
    video_path: Path,
    tools: FFmpegTools,
    *,
    search_start: float = 0.0,
    search_end: float | None = None,
) -> AudioMatch:
    if search_start < 0 or (search_end is not None and search_end <= search_start):
        raise ValueError("广告搜索时间范围无效。")

    coarse_rate = 1000
    coarse_hop = 100
    ad_coarse_samples = _samples(extract_pcm(ad_path, tools, sample_rate=coarse_rate))
    ad_coarse = _rms_frames(ad_coarse_samples, coarse_hop)
    search_duration = None
    if search_end is not None:
        # Include one advertisement duration past the last allowed start so a
        # candidate beginning at search_end still has a complete comparison.
        search_duration = search_end - search_start + len(ad_coarse_samples) / coarse_rate
    video_coarse = _rms_frames(
        _samples(
            extract_pcm(
                video_path,
                tools,
                sample_rate=coarse_rate,
                start=search_start,
                duration=search_duration,
            )
        ),
        coarse_hop,
    )
    candidates = _best_offsets(ad_coarse, video_coarse)

    fine_rate = 8000
    fine_hop = 8
    fine_window = 80
    ad_fine_samples = _samples(extract_pcm(ad_path, tools, sample_rate=fine_rate))
    ad_fine = _rolling_rms(ad_fine_samples, fine_window, fine_hop)
    ad_centered, ad_energy = _center(ad_fine)

    best: tuple[float, float, float, float, int, array] | None = None
    for coarse_offset, coarse_score in candidates:
        coarse_time = search_start + coarse_offset * coarse_hop / coarse_rate
        segment_start = max(0.0, coarse_time - 0.25)
        segment_pcm = extract_pcm(
            video_path,
            tools,
            sample_rate=fine_rate,
            start=segment_start,
            duration=(len(ad_fine_samples) / fine_rate) + 0.5,
        )
        segment = _samples(segment_pcm)

        # A 10 ms RMS window moved every 1 ms gives sub-frame timing without
        # depending on codec packet boundaries.
        fine_series = _rolling_rms(segment, fine_window, fine_hop)

        max_offset = len(fine_series) - len(ad_fine)
        if max_offset < 0:
            continue
        for fine_offset in range(max_offset + 1):
            score = _correlation_at(ad_centered, ad_energy, fine_series, fine_offset)
            start = segment_start + fine_offset * fine_hop / fine_rate
            if start < search_start or (search_end is not None and start > search_end):
                continue
            if best is None or score > best[1]:
                best = (start, score, coarse_score, segment_start, fine_offset, segment)

    if best is None:
        raise ValueError("没有足够的音频数据完成精细匹配。")
    exact_offset, waveform_score = _refine_waveform_offset(
        ad_fine_samples,
        best[5],
        best[4] * fine_hop,
        sample_rate=fine_rate,
    )
    exact_start = best[3] + exact_offset / fine_rate
    return AudioMatch(
        start=exact_start,
        duration=len(ad_fine_samples) / fine_rate,
        score=best[1],
        waveform_score=waveform_score,
        coarse_start=search_start + candidates[0][0] * coarse_hop / coarse_rate,
        coarse_score=best[2],
        search_start=search_start,
        search_end=search_end,
    )

