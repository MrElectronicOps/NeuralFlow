"""Local, timestamp-preserving offline video processing for NeuralFlow.

Only the neural residual is temporally filtered. Input video frames themselves
are never averaged. The caller owns exclusive access to the neural backend.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from fractions import Fraction

VENDOR = Path(__file__).resolve().parent / "vendor"
if VENDOR.is_dir():
    sys.path.insert(0, str(VENDOR))

try:
    import av
except ImportError:
    av = None
import cv2
import numpy as np
from PIL import Image

cv2.setNumThreads(2)
TILE_SIZE = 512
TIME_BASE = Fraction(1, 90000)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Cancelled(Exception):
    """A user cancelled the job; no final output was published."""


def _cancel(cancel):
    if cancel.is_set():
        raise Cancelled("Video preparation cancelled.")


def ffmpeg_path():
    """Resolve a bundled tool or an explicit installation; no personal paths."""
    configured = os.environ.get("NEURALFLOW_FFMPEG")
    candidates = [Path(configured)] if configured else []
    candidates += [Path(__file__).resolve().parent / "tools" / "ffmpeg.exe"]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    system = shutil.which("ffmpeg")
    if system:
        return system
    raise RuntimeError("The video tools are missing. Reinstall NeuralFlow Preview.")


def _require_video_tools():
    global av
    if av is None:
        try:
            import importlib
            av = importlib.import_module("av")
        except ImportError as exc:
            raise RuntimeError("Install video tools from NeuralFlow System before preparing videos.") from exc


def positions(length, size=TILE_SIZE):
    if length < 1:
        raise ValueError("Video dimensions must be positive.")
    return sorted(set([*range(0, max(1, length - size + 1), size - 64), max(0, length - size)]))


def neural_frame(source, backend, cancel):
    """Evaluate overlapping native-resolution tiles; feather their borders."""
    source = source.convert("RGB")
    width, height = source.size
    total = np.zeros((height, width, 3), np.float32)
    weights = np.zeros((height, width, 1), np.float32)
    evaluations = 0
    neural_ms = 0.0
    for y in positions(height):
        for x in positions(width):
            _cancel(cancel)
            tile = source.crop((x, y, min(x + TILE_SIZE, width), min(y + TILE_SIZE, height)))
            tw, th = tile.size
            padded = np.pad(np.asarray(tile), ((0, TILE_SIZE - th), (0, TILE_SIZE - tw), (0, 0)), mode="edge")
            output, metrics = backend.render(Image.fromarray(padded), cancel=cancel)
            _cancel(cancel)
            if output.size != (TILE_SIZE, TILE_SIZE):
                raise RuntimeError("The neural worker returned an invalid video tile.")
            rendered = np.asarray(output.convert("RGB"), dtype=np.float32)[:th, :tw]
            if not np.isfinite(rendered).all():
                raise RuntimeError("The neural worker returned non-finite pixels.")
            wx = np.minimum(1.0, np.minimum(np.arange(tw) + 1, tw - np.arange(tw)) / 32)
            wy = np.minimum(1.0, np.minimum(np.arange(th) + 1, th - np.arange(th)) / 32)
            weight = (wy[:, None] * wx[None, :])[:, :, None]
            total[y:y + th, x:x + tw] += rendered * weight
            weights[y:y + th, x:x + tw] += weight
            evaluations += 1
            neural_ms += float(metrics.get("evaluation_ms", metrics.get("ms", 0)))
    return total / weights, {"evaluations": evaluations, "neural_ms": neural_ms}


class ResidualStabilizer:
    """Bidirectional optical flow with occlusion rejection and cut resets.

    Flow uses at most 640 pixels across; the residual stays at native resolution.
    Confidence includes colour agreement and forward/backward flow consistency.
    """
    def __init__(self, stability=.75):
        self.stability = float(np.clip(stability, 0, 1))
        self.previous = None
        self.history = None
        self.cuts = 0
        self.confidence = 0.0

    def apply(self, source, neural, strength):
        original = np.asarray(source.convert("RGB"), dtype=np.float32)
        residual = np.asarray(neural, dtype=np.float32) - original
        if residual.shape != original.shape or not np.isfinite(residual).all():
            raise ValueError("Invalid neural residual.")
        if strength == 0:
            self.previous = None
            self.history = None
            return source.copy()
        if self.previous is None or self.previous.shape != original.shape or self.stability == 0:
            blended = residual
            self.confidence = 0.0
        else:
            height, width = original.shape[:2]
            scale = min(1.0, 640 / width, 360 / height)
            small_size = (max(16, round(width * scale)), max(16, round(height * scale)))
            previous = cv2.resize(self.previous, small_size, interpolation=cv2.INTER_AREA)
            current = cv2.resize(original, small_size, interpolation=cv2.INTER_AREA)
            previous_gray = cv2.cvtColor(previous.astype(np.uint8), cv2.COLOR_RGB2GRAY)
            current_gray = cv2.cvtColor(current.astype(np.uint8), cv2.COLOR_RGB2GRAY)
            if np.array_equal(previous, current):
                history = self.history
                confidence = np.ones((height, width), np.float32)
                cut = False
            else:
                backward = cv2.calcOpticalFlowFarneback(current_gray, previous_gray, None, .5, 4, 21, 3, 7, 1.5, 0)
                forward = cv2.calcOpticalFlowFarneback(previous_gray, current_gray, None, .5, 4, 21, 3, 7, 1.5, 0)
                sy, sx = current_gray.shape
                xx, yy = np.meshgrid(np.arange(sx, dtype=np.float32), np.arange(sy, dtype=np.float32))
                maps = np.stack((xx, yy), axis=-1) + backward
                warped_source = cv2.remap(previous, maps, None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
                warped_forward = cv2.remap(forward, maps, None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
                error = np.mean(np.abs(current - warped_source), axis=2)
                cycle = np.linalg.norm(backward + warped_forward, axis=2)
                valid = (maps[:, :, 0] >= 0) & (maps[:, :, 0] < sx - 1) & (maps[:, :, 1] >= 0) & (maps[:, :, 1] < sy - 1)
                confidence_small = np.clip(1 - error / 24, 0, 1) * np.clip(1 - cycle / 1.8, 0, 1) * valid
                cut = float(error.mean()) > 32 and float(confidence_small.mean()) < .22
                full_flow = cv2.resize(backward, (width, height), interpolation=cv2.INTER_LINEAR)
                full_flow *= np.array([width / sx, height / sy], dtype=np.float32)
                xx, yy = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
                full_maps = np.stack((xx, yy), axis=-1) + full_flow
                history = cv2.remap(self.history, full_maps, None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
                confidence = cv2.resize(confidence_small, (width, height), interpolation=cv2.INTER_LINEAR)
            if cut:
                blended = residual
                self.cuts += 1
                self.confidence = 0.0
            else:
                self.confidence = float(confidence.mean())
                history_weight = .85 * self.stability * confidence[:, :, None]
                # Reject major detail disagreement locally to limit lingering hallucinations.
                disagreement = np.max(np.abs(history - residual), axis=2, keepdims=True)
                history_weight *= np.clip(1 - np.maximum(0, disagreement - 32) / 64, 0, 1)
                blended = residual + (history - residual) * history_weight
        self.previous = original
        self.history = blended
        return Image.fromarray(np.clip(np.rint(original + blended * strength), 0, 255).astype(np.uint8))


def _run(command, cancel, log_path):
    _cancel(cancel)
    with open(log_path, "ab") as errors:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=errors, creationflags=CREATE_NO_WINDOW)
        try:
            while process.poll() is None:
                _cancel(cancel)
                time.sleep(.05)
            if process.returncode:
                raise RuntimeError("Video tools failed. See the render log: " + str(log_path))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def _validate_paths(source, destination):
    source = Path(source).expanduser().resolve(strict=True)
    destination = Path(destination).expanduser().resolve()
    if source == destination or destination.exists():
        raise ValueError("Choose a new output filename. Existing files are never overwritten.")
    if destination.suffix.lower() not in (".mkv", ".mp4"):
        raise ValueError("Choose an MP4 or MKV output file.")
    if not destination.parent.is_dir():
        raise ValueError("The output folder does not exist.")
    return source, destination


def _publish(partial, destination):
    # Windows rename does not overwrite an existing file. Hard-link publication
    # supplies the same no-clobber contract on other supported local filesystems.
    if os.name == "nt":
        partial.rename(destination)
    else:
        os.link(partial, destination)
        partial.unlink()


def _timestamp(frame):
    if frame.pts is None or frame.time_base is None:
        raise ValueError("This video has missing frame timestamps; it cannot be rendered without changing its timing.")
    return frame.pts * frame.time_base


def _frame_duration(frame, following, previous_duration, fallback):
    if following is not None:
        duration = _timestamp(following) - _timestamp(frame)
    elif frame.duration and frame.time_base:
        duration = frame.duration * frame.time_base
    else:
        duration = previous_duration or fallback
    if duration <= 0:
        raise ValueError("This video has duplicate or reversed timestamps.")
    return duration


def _verify_output(path, expected_times, expected_end, expected_audio, cancel, ffmpeg, log_path):
    _run([ffmpeg, "-hide_banner", "-v", "error", "-xerror", "-nostdin", "-i", str(path),
          "-map", "0:v", "-map", "0:a?", "-f", "null", "-"], cancel, log_path)
    max_error = 0.0
    end = 0.0
    count = 0
    with av.open(str(path)) as check:
        if len(check.streams.audio) != expected_audio:
            raise RuntimeError("The rendered file is missing an audio track.")
        for frame in check.decode(video=0):
            _cancel(cancel)
            if count >= len(expected_times):
                raise RuntimeError("Output verification found extra video frames.")
            actual = float(_timestamp(frame))
            error = abs(actual - expected_times[count])
            max_error = max(max_error, error)
            if error > .002:
                raise RuntimeError("Output verification found changed frame timing.")
            end = actual + float(frame.duration * frame.time_base if frame.duration else 0)
            count += 1
    if count != len(expected_times):
        raise RuntimeError("The rendered file is missing video frames.")
    if end and abs(end - expected_end) > .003:
        raise RuntimeError("Output verification found a changed final frame duration.")
    return {"frames": count, "max_timestamp_error_ms": round(max_error * 1000, 4),
            "duration_error_ms": round(abs(end - expected_end) * 1000, 4), "full_decode_verified": True}


def export_video(source, destination, strength, stability, backend, cancel, progress):
    """Render every input frame, preserve its PTS, mux source audio, verify.

    Progress receives dictionaries with stage, frames, estimated_frames, elapsed,
    seconds_per_frame, media_seconds, duration_seconds, evaluations and scene_cuts.
    Strength/stability are fractions in [0, 1]. backend is unnecessary at zero.
    """
    source, destination = _validate_paths(source, destination)
    _require_video_tools()
    strength, stability = float(strength), float(stability)
    if not math.isfinite(strength) or not math.isfinite(stability) or not 0 <= strength <= 1 or not 0 <= stability <= 1:
        raise ValueError("Neural strength and stability must be between zero and one.")
    _cancel(cancel)
    ffmpeg = ffmpeg_path()
    log_path = destination.with_name(destination.name + ".render.log")
    if log_path.exists():
        raise ValueError("The render log already exists; choose a new output filename.")
    started = time.monotonic()
    count = evaluations = 0
    expected_times = []
    previous_duration = None
    stabilizer = ResidualStabilizer(stability)
    progress({"stage": "checking", "frames": 0, "elapsed": 0})
    with tempfile.TemporaryDirectory(prefix=".neuralflow-video-", dir=str(destination.parent)) as work:
        work = Path(work)
        intermediate = work / ("video" + destination.suffix.lower())
        partial = work / ("complete" + destination.suffix.lower())
        with av.open(str(source)) as reader:
            if not reader.streams.video:
                raise ValueError("The selected file contains no video.")
            stream = reader.streams.video[0]
            codec = stream.codec_context
            if codec.format and any(component.bits > 8 for component in codec.format.components):
                raise ValueError("This beta supports 8-bit SDR video. Convert HDR or high-bit-depth video to SDR first.")
            if int(codec.color_trc) in (16, 18):
                raise ValueError("HDR video is not supported by this SDR renderer.")
            width, height = codec.width, codec.height
            if destination.suffix.lower() == ".mp4" and (width % 2 or height % 2):
                raise ValueError("This video has odd dimensions. Choose lossless MKV to preserve its full frame.")
            if width * height > 3840 * 2160:
                raise ValueError("This beta supports offline video up to 3840 × 2160 pixels.")
            rate = stream.average_rate or stream.guessed_rate or Fraction(30)
            fallback_duration = Fraction(1, 1) / rate
            audio_count = len(reader.streams.audio)
            iterator = iter(reader.decode(video=0))
            frame = next(iterator, None)
            if frame is None:
                raise ValueError("The selected video has no decodable frames.")
            first_video = _timestamp(frame)
            starts = [first_video]
            starts += [s.start_time * s.time_base for s in reader.streams.audio if s.start_time is not None]
            origin = min(starts)
            duration_seconds = float(reader.duration / av.time_base) if reader.duration else 0
            estimated = stream.frames or (round(duration_seconds * float(rate)) if duration_seconds else 0)
            container_options = {"video_track_timescale": "90000", "movie_timescale": "90000"} if destination.suffix.lower() == ".mp4" else {}
            with av.open(str(intermediate), mode="w", container_options=container_options) as writer:
                output = writer.add_stream("libx264" if destination.suffix.lower() == ".mp4" else "ffv1", rate=rate)
                output.width, output.height = width, height
                output.pix_fmt = "yuv420p" if destination.suffix.lower() == ".mp4" else "bgr0"
                output.time_base = TIME_BASE
                output.codec_context.time_base = TIME_BASE
                output.codec_context.thread_count = 2
                output.codec_context.max_b_frames = 0
                output.codec_context.flags |= av.codec.context.Flags.frame_duration
                output.sample_aspect_ratio = stream.sample_aspect_ratio or Fraction(1)
                output.options = {"preset": "slow", "crf": "16", "tune": "zerolatency"} if destination.suffix.lower() == ".mp4" else {"level": "3"}
                duration_by_pts = {}

                def mux_packets(packets):
                    for packet in packets:
                        packet_time = packet.pts * packet.time_base if packet.pts is not None else None
                        packet_duration = duration_by_pts.pop(packet_time, None)
                        if packet_duration is not None:
                            packet.duration = max(1, round(packet_duration / packet.time_base))
                        writer.mux(packet)

                while frame is not None:
                    _cancel(cancel)
                    following = next(iterator, None)
                    duration = _frame_duration(frame, following, previous_duration, fallback_duration)
                    stamp = _timestamp(frame) - origin
                    if expected_times and float(stamp) <= expected_times[-1]:
                        raise ValueError("Video timestamps are not strictly increasing.")
                    original = frame.to_image().convert("RGB")
                    if original.size != (width, height):
                        raise ValueError("Changing video dimensions are not supported in this beta.")
                    if strength:
                        rendered, metrics = neural_frame(original, backend, cancel)
                        enhanced = stabilizer.apply(original, rendered, strength)
                        evaluations += metrics["evaluations"]
                    else:
                        enhanced = original
                    _cancel(cancel)
                    encoded = av.VideoFrame.from_image(enhanced)
                    encoded.time_base = TIME_BASE
                    encoded.pts = round(stamp / TIME_BASE)
                    encoded.duration = max(1, round(duration / TIME_BASE))
                    duration_by_pts[encoded.pts * TIME_BASE] = duration
                    mux_packets(output.encode(encoded))
                    count += 1
                    expected_times.append(float(stamp))
                    expected_end = float(stamp + duration)
                    elapsed = time.monotonic() - started
                    progress({"stage": "rendering", "frames": count, "estimated_frames": estimated,
                              "elapsed": elapsed, "seconds_per_frame": elapsed / count,
                              "media_seconds": float(stamp), "duration_seconds": duration_seconds,
                              "evaluations": evaluations, "tiles_per_frame": len(positions(width)) * len(positions(height)),
                              "scene_cuts": stabilizer.cuts})
                    frame, previous_duration = following, duration
                mux_packets(output.encode(None))
        progress({"stage": "audio", "frames": count, "elapsed": time.monotonic() - started})
        audio_codec = ["-c:a", "copy"] if destination.suffix.lower() == ".mkv" else ["-c:a", "aac", "-b:a", "192k"]
        mux_command = [ffmpeg, "-hide_banner", "-v", "warning", "-nostdin", "-n", "-copyts", "-i", str(intermediate),
                       "-itsoffset", format(-float(origin), ".12f"), "-i", str(source),
                       "-map", "0:v:0", "-map", "1:a?", "-map_metadata", "1", "-map_chapters", "-1",
                       "-c:v", "copy", *audio_codec, "-avoid_negative_ts", "disabled", "-threads", "2"]
        if destination.suffix.lower() == ".mp4":
            mux_command += ["-movflags", "+faststart", "-video_track_timescale", "90000"]
        _run(mux_command + [str(partial)], cancel, log_path)
        progress({"stage": "verifying", "frames": count, "elapsed": time.monotonic() - started})
        verified = _verify_output(partial, expected_times, expected_end, audio_count, cancel, ffmpeg, log_path)
        _cancel(cancel)
        _publish(partial, destination)
    report = {"path": str(destination), "frames": count, "size": [width, height],
              "strength": strength, "stability": stability, "seconds": round(time.monotonic() - started, 3),
              "evaluations": evaluations, "native_resolution_tiles": True, "temporal_stabilization": stability > 0 and strength > 0,
              "temporal_model_inputs": False, "scene_cuts": stabilizer.cuts, "source_timestamps_preserved": True,
              "timeline_origin_seconds": float(origin), "duration_seconds": expected_end,
              "audio_tracks": audio_count, "audio": "copy" if destination.suffix.lower() == ".mkv" else "AAC 192k",
              **verified}
    # The media is already complete; a sidecar failure must not report rendering as failed.
    try:
        with destination.with_name(destination.name + ".json").open("x", encoding="utf-8") as sidecar:
            json.dump(report, sidecar, indent=2)
    except OSError as exc:
        report["report_warning"] = str(exc)
    progress({"stage": "ready", **report})
    return report


def prepare_playback(source, destination, cancel, progress):
    """Create an H.264/AAC proxy suitable for Windows MediaElement playback.

    It uses the same frame-preserving path at zero neural strength. Odd-sized
    originals must first be exported to MKV; proxy padding is deliberately not
    implicit because it would break pixel-aligned comparison.
    """
    if Path(destination).suffix.lower() != ".mp4":
        raise ValueError("Playback proxies use MP4 files.")
    result = export_video(source, destination, 0, 0, None, cancel, progress)
    result["playback_proxy"] = True
    return result
