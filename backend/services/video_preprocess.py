from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class VideoPreprocessResult:
    modality: str
    duration_ms: int | None
    width_px: int | None
    height_px: int | None
    frame_rate: float | None
    sampled_frame_paths: list[str]
    audio_path: str | None
    preprocessing_summary: dict
    extracted_metadata: dict
    temp_dir: str | None = None

    def cleanup(self) -> None:
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)


class VideoPreprocessService:
    """
    Requires ffprobe and ffmpeg available on PATH for full functionality.
    Falls back gracefully if they are missing or the input cannot be decoded.
    """

    def probe(self, input_path: str) -> dict:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            input_path,
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(completed.stdout)

    def sample_frames(
        self,
        *,
        input_path: str,
        output_dir: str,
        max_frames: int = 8,
    ) -> list[str]:
        pattern = os.path.join(output_dir, "frame_%03d.jpg")
        fps_filter = f"fps={max(1, max_frames // 4)}"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-vf",
            fps_filter,
            "-frames:v",
            str(max_frames),
            pattern,
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return sorted(str(path) for path in Path(output_dir).glob("frame_*.jpg"))

    def extract_audio(
        self,
        *,
        input_path: str,
        output_path: str,
    ) -> str | None:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            output_path,
        ]
        completed = subprocess.run(cmd, capture_output=True)
        if completed.returncode != 0:
            return None
        return output_path

    def preprocess(
        self,
        *,
        input_path: str,
        max_frames: int = 8,
    ) -> VideoPreprocessResult:
        tmp_dir = tempfile.mkdtemp(prefix="tribe_video_")
        frame_dir = os.path.join(tmp_dir, "frames")
        os.makedirs(frame_dir, exist_ok=True)
        audio_path = os.path.join(tmp_dir, "audio.wav")

        duration_ms = None
        width_px = None
        height_px = None
        frame_rate = None
        probe_data: dict = {}

        try:
            probe_data = self.probe(input_path)
            for stream in probe_data.get("streams", []):
                if stream.get("codec_type") != "video":
                    continue
                width_px = stream.get("width")
                height_px = stream.get("height")
                r_frame_rate = stream.get("r_frame_rate")
                if r_frame_rate and "/" in r_frame_rate:
                    numerator, denominator = r_frame_rate.split("/", 1)
                    if float(denominator) != 0:
                        frame_rate = float(numerator) / float(denominator)
                break

            if probe_data.get("format", {}).get("duration"):
                duration_ms = int(float(probe_data["format"]["duration"]) * 1000)
        except Exception:
            probe_data = {}

        try:
            sampled_frame_paths = self.sample_frames(
                input_path=input_path, output_dir=frame_dir, max_frames=max_frames
            )
        except Exception:
            sampled_frame_paths = []

        try:
            extracted_audio_path = self.extract_audio(input_path=input_path, output_path=audio_path)
        except Exception:
            extracted_audio_path = None

        return VideoPreprocessResult(
            modality="video",
            duration_ms=duration_ms,
            width_px=width_px,
            height_px=height_px,
            frame_rate=frame_rate,
            sampled_frame_paths=sampled_frame_paths,
            audio_path=extracted_audio_path,
            preprocessing_summary={
                "status": "ready",
                "pipeline_version": "video_v2",
                "sampled_frame_count": len(sampled_frame_paths),
                "audio_extracted": extracted_audio_path is not None,
            },
            extracted_metadata={
                "duration_ms": duration_ms,
                "width_px": width_px,
                "height_px": height_px,
                "frame_rate": frame_rate,
                "probe_data": probe_data,
            },
            temp_dir=tmp_dir,
        )
