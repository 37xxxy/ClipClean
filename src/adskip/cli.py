from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .cutter import build_cut_plan, create_boundary_previews, cut_video, prepare_ad_reference
from .detector import DetectionResult, detect_ad, load_ad_profile
from .ffmpeg import FFmpegError, FFmpegTools, find_tools, probe


def _path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"文件不存在：{path}")
    return path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adskip", description="固定广告自动定位工具")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("doctor", help="检查 FFmpeg 环境")

    prepare = commands.add_parser("prepare-ad", help="从含前后正片的片段制作纯广告基准")
    prepare.add_argument("--source", required=True, type=_path, help="包含完整广告的来源片段")
    prepare.add_argument("--start-frame", type=int, help="广告第一帧")
    prepare.add_argument("--end-frame", type=int, help="广告结束后的第一帧")
    prepare.add_argument("--start-time", type=float, help="广告开始时间（秒）")
    prepare.add_argument("--end-time", type=float, help="广告结束时间（秒）")
    prepare.add_argument("--output", required=True, type=Path, help="纯广告基准输出路径")

    detect = commands.add_parser("detect", help="在视频中定位广告（不会修改视频）")
    detect.add_argument("--ad", required=True, type=_path, help="完整广告样本")
    detect.add_argument("--video", required=True, type=_path, help="待检测视频")
    detect.add_argument("--output", required=True, type=Path, help="JSON 报告路径")
    _add_search_options(detect)

    cut = commands.add_parser("cut", help="检测并删除广告，输出新视频")
    cut.add_argument("--ad", required=True, type=_path, help="完整广告样本")
    cut.add_argument("--video", required=True, type=_path, help="待处理视频")
    cut.add_argument("--output", required=True, type=Path, help="新视频输出路径")
    cut.add_argument("--report", type=Path, help="JSON 报告路径（默认跟随输出视频）")
    cut.add_argument("--preview-dir", type=Path, help="边界预览目录（默认跟随输出视频）")
    _add_search_options(cut)
    cut.add_argument(
        "--mode",
        choices=("audio-safe", "precise"),
        default="audio-safe",
        help="剪切策略，默认 audio-safe（音频零残留优先）",
    )
    cut.add_argument(
        "--leading-guard-frames",
        type=_non_negative_int,
        default=3,
        help="广告开始前额外删除的画面帧数，默认 3",
    )
    cut.add_argument(
        "--trailing-guard-frames",
        type=_non_negative_int,
        default=2,
        help="广告结束后额外删除的画面帧数，默认 2",
    )
    cut.add_argument(
        "--safety-guard-frames",
        type=_non_negative_int,
        default=1,
        help="音画共同区间两侧的总安全余量帧数，默认 1",
    )
    return parser


def _add_search_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--search-start-ratio",
        type=float,
        default=0.35,
        help="广告起点搜索范围的开始比例，默认 0.35",
    )
    parser.add_argument(
        "--search-end-ratio",
        type=float,
        default=0.65,
        help="广告起点搜索范围的结束比例，默认 0.65",
    )
    parser.add_argument(
        "--full-scan",
        action="store_true",
        help="忽略搜索比例，扫描整段视频",
    )


def _non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0 or number > 30:
        raise argparse.ArgumentTypeError("帧数必须在 0 到 30 之间。")
    return number


def _doctor() -> int:
    tools = find_tools()
    print(f"FFmpeg : {tools.ffmpeg}")
    print(f"FFprobe: {tools.ffprobe}")
    print("环境检查通过。")
    return 0


def _prepare_ad(args: argparse.Namespace) -> int:
    tools = find_tools()
    output = args.output.expanduser().resolve()
    if args.start_time is not None or args.end_time is not None:
        if args.start_time is None or args.end_time is None:
            raise ValueError("开始时间和结束时间必须同时提供。")
        if args.start_frame is not None or args.end_frame is not None:
            raise ValueError("时间参数和帧参数不能混用。")
        source_info = probe(args.source, tools)
        start_frame = round(args.start_time * source_info.fps)
        end_frame = round(args.end_time * source_info.fps)
    else:
        if args.start_frame is None or args.end_frame is None:
            raise ValueError("请提供开始/结束时间，或开始/结束帧。")
        start_frame = args.start_frame
        end_frame = args.end_frame
    prepared = prepare_ad_reference(
        args.source,
        tools,
        output,
        start_frame=start_frame,
        end_frame_exclusive=end_frame,
    )
    print(f"纯广告基准已生成：{prepared}")
    print(f"广告帧区间：[{start_frame}, {end_frame})")
    return 0


def _analyze(
    ad: Path,
    video: Path,
    tools: FFmpegTools,
    *,
    search_start_ratio: float,
    search_end_ratio: float,
) -> DetectionResult:
    _, _, profile_path = load_ad_profile(ad)
    if profile_path:
        print(f"已加载广告配置：{profile_path}", flush=True)
    print("正在提取音频并搜索广告位置……", flush=True)
    print(
        f"广告起点搜索范围：视频时长的 {search_start_ratio:.0%} - {search_end_ratio:.0%}",
        flush=True,
    )
    result = detect_ad(
        ad,
        video,
        tools,
        search_start_ratio=search_start_ratio,
        search_end_ratio=search_end_ratio,
    )
    print("正在逐帧验证候选边界……", flush=True)
    return result


def _print_result(result: DetectionResult) -> None:
    print(f"候选区间：{result.start:.3f}s - {result.end:.3f}s")
    print(
        f"检测流参考帧：[{result.start_frame}, {result.end_frame_exclusive}) "
        "（仅供诊断，正式剪切使用时间戳）"
    )
    print(
        "音频/画面/综合分："
        f"{result.audio.score:.4f} / {result.video.score:.4f} / {result.combined_score:.4f}"
    )
    print(f"可信度：{result.confidence}")


def _write_report(path: Path, report: dict[str, object]) -> Path:
    output = path.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def _detect(args: argparse.Namespace) -> int:
    tools = find_tools()
    start_ratio, end_ratio = _search_ratios(args)
    result = _analyze(
        args.ad,
        args.video,
        tools,
        search_start_ratio=start_ratio,
        search_end_ratio=end_ratio,
    )
    output = _write_report(args.output, result.to_report())
    _print_result(result)
    print(f"报告已写入：{output}")
    return 0


def _cut(args: argparse.Namespace) -> int:
    tools = find_tools()
    start_ratio, end_ratio = _search_ratios(args)
    result = _analyze(
        args.ad,
        args.video,
        tools,
        search_start_ratio=start_ratio,
        search_end_ratio=end_ratio,
    )
    _print_result(result)

    output = args.output.expanduser().resolve()
    report_path = (
        args.report.expanduser().resolve()
        if args.report
        else output.with_suffix(".report.json")
    )
    preview_dir = (
        args.preview_dir.expanduser().resolve()
        if args.preview_dir
        else output.with_name(f"{output.stem}_边界预览")
    )
    plan = build_cut_plan(
        result,
        args.mode,
        video_leading_guard_frames=args.leading_guard_frames,
        video_trailing_guard_frames=args.trailing_guard_frames,
        audio_safe_extra_frames=args.safety_guard_frames,
    )
    print(
        f"画面删除区间：{plan.video_start:.6f}s - {plan.video_end:.6f}s "
        f"（检测流参考帧 [{plan.start_frame}, {plan.end_frame_exclusive})）",
        flush=True,
    )
    print(
        f"音频安全删除区间：{plan.audio_start:.6f}s - {plan.audio_end:.6f}s",
        flush=True,
    )
    print("正在精确剪切并重新编码……", flush=True)
    cut = cut_video(
        result,
        tools,
        output,
        mode=args.mode,
        video_leading_guard_frames=args.leading_guard_frames,
        video_trailing_guard_frames=args.trailing_guard_frames,
        audio_safe_extra_frames=args.safety_guard_frames,
    )
    previews: list[Path] = []
    preview_warning: str | None = None
    print("正在生成边界预览……", flush=True)
    try:
        previews = create_boundary_previews(result, tools, preview_dir, plan)
    except FFmpegError as exc:
        preview_warning = str(exc)
        print(f"警告：边界预览生成失败，但输出视频不受影响：{exc}", flush=True)
    report_data = result.to_report(cut_output=cut.output)
    report_data["cut"] = {
        "mode": cut.plan.mode,
        "coordinate_system": "stream_timestamp_seconds",
        "frame_numbers_are_diagnostic": True,
        "seam_strategy": (
            "shared_audio_video_safe_boundary_without_seam_silence"
            if cut.plan.mode == "audio-safe"
            else "precise_boundaries"
        ),
        "start_frame": cut.plan.start_frame,
        "end_frame_exclusive": cut.plan.end_frame_exclusive,
        "start": round(cut.plan.video_start, 6),
        "end": round(cut.plan.video_end, 6),
        "audio_start": round(cut.plan.audio_start, 6),
        "audio_end": round(cut.plan.audio_end, 6),
        "audio_seam_silence": round(
            max(
                0.0,
                (cut.plan.audio_end - cut.plan.audio_start)
                - (cut.plan.video_end - cut.plan.video_start),
            ),
            6,
        ),
        "audio_seam_fade": 0.002,
        "guards": {
            "leading_frames": args.leading_guard_frames,
            "trailing_frames": args.trailing_guard_frames,
            "safety_frames": args.safety_guard_frames,
        },
        "validation": cut.validation.to_report(),
    }
    if preview_warning:
        report_data["preview_warning"] = preview_warning
    report = _write_report(report_path, report_data)
    print(f"输出视频：{cut.output}")
    print(f"输出时长：{cut.actual_duration:.3f}s（预期约 {cut.expected_duration:.3f}s）")
    print(
        "输出验收：通过；广告整段/开头/结尾残留相似度 "
        f"{cut.validation.residual_ad_score:.4f} / "
        f"{cut.validation.residual_ad_start_score:.4f} / "
        f"{cut.validation.residual_ad_end_score:.4f}，"
        f"音视频尾差 {cut.validation.audio_video_delta:.3f}s",
        flush=True,
    )
    print(f"边界预览：{preview_dir}")
    print(f"处理报告：{report}")
    print(f"已生成 {len(previews)} 张边界预览，原视频未被修改。")
    return 0


def _search_ratios(args: argparse.Namespace) -> tuple[float, float]:
    if args.full_scan:
        return 0.0, 1.0
    return args.search_start_ratio, args.search_end_ratio


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            return _doctor()
        if args.command == "prepare-ad":
            return _prepare_ad(args)
        if args.command == "detect":
            return _detect(args)
        if args.command == "cut":
            return _cut(args)
    except (FFmpegError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

