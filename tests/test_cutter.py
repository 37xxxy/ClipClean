from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from array import array
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adskip.audio_match import AudioMatch
from adskip.cutter import build_cut_plan, cut_video
from adskip.detector import DetectionResult, detect_ad
from adskip.ffmpeg import MediaInfo, extract_pcm, find_tools, probe
from adskip.video_match import VideoMatch


def _detection(
    video: Path,
    info: MediaInfo,
    *,
    start: float,
    end: float,
    ad_path: Path | None = None,
) -> DetectionResult:
    duration = end - start
    return DetectionResult(
        ad_path=ad_path or video,
        video_path=video,
        ad_info=MediaInfo(duration, 30.0, 160, 90, True, 30),
        video_info=info,
        audio=AudioMatch(start, duration, 1.0, 1.0, start, 1.0),
        video=VideoMatch(start, end, info.fps, 1.0),
    )


class CutPlanTests(unittest.TestCase):
    def test_expected_duration_uses_timestamps_not_average_frame_count(self) -> None:
        info = MediaInfo(
            duration=100.0,
            fps=25.0,
            width=160,
            height=90,
            has_audio=True,
            frame_count=3000,
        )
        result = _detection(Path("variable-rate.mp4"), info, start=40.0, end=50.0)

        plan = build_cut_plan(result, mode="precise")

        self.assertEqual(plan.video_start, 40.0)
        self.assertEqual(plan.video_end, 50.0)
        self.assertEqual(plan.expected_duration, 90.0)

    def test_audio_safe_mode_uses_one_shared_interval_without_silence(self) -> None:
        info = MediaInfo(100.0, 25.0, 160, 90, True, 2500)
        result = _detection(Path("seam.mp4"), info, start=40.0, end=50.0)

        plan = build_cut_plan(result, mode="audio-safe")

        self.assertEqual(plan.video_start, 39.84)
        self.assertEqual(plan.video_end, 50.12)
        self.assertEqual(plan.audio_start, 39.84)
        self.assertEqual(plan.audio_end, 50.12)
        self.assertEqual(plan.audio_start, plan.video_start)
        self.assertEqual(plan.audio_end, plan.video_end)


class DetectionSearchRangeTests(unittest.TestCase):
    @patch("adskip.detector.load_ad_profile", return_value=(0.0, 0.0, None))
    @patch("adskip.detector.verify_video")
    @patch("adskip.detector.locate_ad")
    @patch("adskip.detector.probe")
    def test_default_search_is_middle_thirty_percent(
        self,
        probe_mock,
        locate_mock,
        verify_mock,
        _profile_mock,
    ) -> None:
        ad_info = MediaInfo(10.0, 25.0, 160, 90, True, 250)
        video_info = MediaInfo(100.0, 25.0, 160, 90, True, 2500)
        probe_mock.side_effect = [ad_info, video_info]
        locate_mock.return_value = AudioMatch(45.0, 10.0, 1.0, 1.0, 45.0, 1.0)
        verify_mock.return_value = VideoMatch(45.0, 55.0, 25.0, 1.0)

        detect_ad(Path("ad.mp4"), Path("video.mp4"), object())

        self.assertEqual(locate_mock.call_args.kwargs["search_start"], 35.0)
        self.assertEqual(locate_mock.call_args.kwargs["search_end"], 65.0)


class VariableFrameRateIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.tools = find_tools()
        except Exception as exc:  # pragma: no cover - environment-specific skip
            raise unittest.SkipTest(str(exc)) from exc

    def _run_ffmpeg(self, *arguments: str) -> None:
        completed = subprocess.run(
            [str(self.tools.ffmpeg), "-hide_banner", "-loglevel", "error", "-y", *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode:
            self.fail(completed.stderr.decode("utf-8", errors="replace"))

    def _make_segment(
        self,
        path: Path,
        *,
        color: str,
        fps: int,
        duration: float,
        tone: int,
    ) -> None:
        self._run_ffmpeg(
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=160x90:r={fps}:d={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={tone}:sample_rate=48000:duration={duration}",
            "-shortest",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        )

    def test_timestamp_cut_removes_all_ad_frames_from_vfr_video(self) -> None:
        with tempfile.TemporaryDirectory() as directory_text:
            directory = Path(directory_text)
            pre = directory / "pre.mp4"
            ad = directory / "ad.mp4"
            post = directory / "post.mp4"
            source = directory / "source-vfr.mp4"
            output = directory / "output.mp4"
            self._make_segment(pre, color="red", fps=15, duration=2.0, tone=300)
            self._make_segment(ad, color="green", fps=30, duration=1.0, tone=1000)
            self._make_segment(post, color="blue", fps=20, duration=2.0, tone=500)

            concat_list = directory / "segments.txt"
            concat_list.write_text(
                "".join(f"file '{path.as_posix()}'\n" for path in (pre, ad, post)),
                encoding="utf-8",
            )
            self._run_ffmpeg(
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c",
                "copy",
                str(source),
            )

            info = probe(source, self.tools)
            self.assertNotEqual(info.frame_count, round(info.duration * 15))
            detection = _detection(source, info, start=2.0, end=3.0, ad_path=ad)
            result = cut_video(detection, self.tools, output, mode="audio-safe")

            rgb = subprocess.run(
                [
                    str(self.tools.ffmpeg),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(output),
                    "-an",
                    "-vf",
                    "scale=1:1:flags=area,format=rgb24",
                    "-f",
                    "rawvideo",
                    "-",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout
            colors = [tuple(rgb[index : index + 3]) for index in range(0, len(rgb), 3)]
            green_frames = [
                color for color in colors if color[1] > color[0] + 35 and color[1] > color[2] + 35
            ]

            self.assertTrue(colors)
            self.assertFalse(green_frames)
            self.assertTrue(any(red > blue + 35 for red, _, blue in colors))
            self.assertTrue(any(blue > red + 35 for red, _, blue in colors))
            self.assertAlmostEqual(result.actual_duration, result.expected_duration, delta=0.15)
            self.assertEqual(result.plan.audio_start, result.plan.video_start)
            self.assertEqual(result.plan.audio_end, result.plan.video_end)

            pcm = array("h")
            pcm.frombytes(
                extract_pcm(
                    output,
                    self.tools,
                    sample_rate=8000,
                    start=max(0.0, result.plan.video_start - 0.1),
                    duration=0.2,
                )
            )
            longest_silence = current_silence = 0
            for sample in pcm:
                if abs(sample) <= 2:
                    current_silence += 1
                    longest_silence = max(longest_silence, current_silence)
                else:
                    current_silence = 0
            self.assertLess(longest_silence / 8000, 0.02)


if __name__ == "__main__":
    unittest.main()
