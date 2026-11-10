"""
Process a local video file:
1. Extract audio to 16kHz WAV.
2. Transcribe locally using faster-whisper with timestamp cues.
3. Generate contact sheets and index.md with extract_frames.py.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Ensure local ffmpeg path is on PATH
FFMPEG_DIR = r"C:\Program Files\Xender Download\ffmpeg"
if os.path.exists(FFMPEG_DIR) and FFMPEG_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

def extract_audio(video_path: str, wav_path: str):
    print(f"[1/3] Extracting audio to {wav_path}...")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le",
        wav_path
    ]
    subprocess.run(cmd, check=True)
    print("      Audio extraction complete.")

def transcribe_audio(wav_path: str, transcript_path: str, model_size: str = "small"):
    print(f"[2/3] Transcribing audio with faster-whisper ({model_size} model on local CPU)...")
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(wav_path, beam_size=5, vad_filter=True)
    print(f"      Detected language: {info.language} (probability: {info.language_probability:.2f})")

    os.makedirs(os.path.dirname(transcript_path), exist_ok=True)
    count = 0
    with open(transcript_path, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(f"[{seg.start:.1f}-{seg.end:.1f}] {seg.text.strip()}\n")
            count += 1
    print(f"      Transcription complete: {count} cues written to {transcript_path}")

def extract_contact_sheets(video_path: str, transcript_path: str, slug: str, interval: int = 15):
    print(f"[3/3] Generating contact sheets at {interval}s interval...")
    script = os.path.join(os.path.dirname(__file__), "knowledge-base", "tools", "extract_frames.py")
    cmd = [
        sys.executable, script, "sheets",
        "--video", video_path,
        "--transcript", transcript_path,
        "--name", slug,
        "--interval", str(interval)
    ]
    subprocess.run(cmd, check=True)
    print(f"      Contact sheets and index generated in knowledge-base/frames/{slug}/")

def main():
    parser = argparse.ArgumentParser(description="Process local video for knowledge-base")
    parser.add_argument("--video", required=True, help="Path to local video file")
    parser.add_argument("--slug", default="asm-intermediate-timeframe-asm", help="Slug name for output directories")
    parser.add_argument("--model", default="small", help="Whisper model size (tiny, base, small, medium)")
    parser.add_argument("--interval", type=int, default=15, help="Frame sample interval in seconds")
    args = parser.parse_args()

    video_path = os.path.abspath(args.video)
    if not os.path.isfile(video_path):
        sys.exit(f"Error: Video file not found: {video_path}")

    repo_dir = os.path.dirname(os.path.abspath(__file__))
    transcript_path = os.path.join(repo_dir, "knowledge-base", "videos", args.slug, "transcript.txt")

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = os.path.join(tmpdir, "audio.wav")
        extract_audio(video_path, wav_path)
        transcribe_audio(wav_path, transcript_path, model_size=args.model)
        extract_contact_sheets(video_path, transcript_path, args.slug, interval=args.interval)

    print("\nSUCCESS: All local processing completed successfully!")

if __name__ == "__main__":
    main()

