"""Render an evidence replay to an MP4 for X (spec §8.4, E12).

    uv run python -m viz.render_video runs/E-0005/q-....json.gz out.mp4 [--aspect square|wide]

Records the replay's ?autoplay=1 run in headless Chromium (captions are drawn by the page,
so they're burned into the frames), then encodes H.264 High / yuv420p / 30 fps / closed
GOP with a silent AAC track, and validates the file against config/x_media.yaml.
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

from lab import paths

LIMITS = paths.CONFIG / "x_media.yaml"


def limits() -> dict:
    return yaml.safe_load(LIMITS.read_text())


def load_transcript(p: Path) -> dict:
    raw = gzip.decompress(p.read_bytes()) if p.suffix == ".gz" else p.read_bytes()
    return json.loads(raw)


def record(transcript: dict, workdir: Path, aspect: str = "square", variant: str | None = None,
           timeout_s: float = 90.0) -> Path:
    from playwright.sync_api import sync_playwright

    from lab.scoring.glance import card_server
    w, h = limits()["target"][aspect]
    with card_server() as base, sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1,
                                  record_video_dir=str(workdir),
                                  record_video_size={"width": w, "height": h})
        page = ctx.new_page()
        page.route("**/__video_transcript.json", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(transcript)))
        url = (f"{base}/replay/index.html?autoplay=1&captions=1&aspect={aspect}"
               f"&t=/__video_transcript.json" + (f"&variant={variant}" if variant else ""))
        page.goto(url)
        page.wait_for_selector("body[data-done='1']", timeout=timeout_s * 1000)
        page.wait_for_timeout(1500)                  # hold the verdict on screen
        video = page.video
        ctx.close()
        browser.close()
        return Path(video.path())


def encode(webm: Path, out: Path, fps: int = 30, trim_start_s: float = 0.3) -> Path:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg not found")
    cmd = [ff, "-y", "-loglevel", "error", "-ss", f"{trim_start_s}", "-i", str(webm),
           "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
           "-map", "0:v:0", "-map", "1:a:0", "-shortest",
           "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(fps),
           "-b:v", "5500k", "-minrate", "5000k", "-maxrate", "8000k", "-bufsize", "10000k",
           "-g", str(fps * 2), "-flags", "+cgop", "-x264-params", "open-gop=0",
           "-c:a", "aac", "-profile:a", "aac_low", "-b:a", "128k",
           "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    return out


def probe(p: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json",
                        str(p)], check=True, capture_output=True, text=True)
    return json.loads(r.stdout)


def validate(p: Path, lim: dict | None = None) -> list[str]:
    """Problems with this file under X's limits ([] means OK to upload)."""
    v = (lim or limits())["video"]
    info = probe(p)
    vs = [s for s in info["streams"] if s["codec_type"] == "video"]
    aus = [s for s in info["streams"] if s["codec_type"] == "audio"]
    out = []
    if len(vs) != 1:
        return ["expected exactly one video stream"]
    s = vs[0]
    num, den = (int(x) for x in s["avg_frame_rate"].split("/"))
    fps = num / den if den else 0
    w, h = int(s["width"]), int(s["height"])
    dur = float(info["format"]["duration"])
    size = int(info["format"]["size"])
    if s["codec_name"] != v["codec"]:
        out.append(f"codec {s['codec_name']} ≠ {v['codec']}")
    if s.get("pix_fmt") != v["pix_fmt"]:
        out.append(f"pixel format {s.get('pix_fmt')} ≠ {v['pix_fmt']}")
    if fps > v["max_fps"]:
        out.append(f"{fps:.1f} fps > {v['max_fps']}")
    if not (v["min_width"] <= w <= v["max_width"] and v["min_height"] <= h <= v["max_height"]):
        out.append(f"{w}x{h} outside {v['min_width']}x{v['min_height']}.."
                   f"{v['max_width']}x{v['max_height']}")
    if not v["aspect_min"] <= w / h <= v["aspect_max"]:
        out.append(f"aspect {w / h:.2f} outside limits")
    if not v["min_duration_s"] <= dur <= v["max_duration_s"]:
        out.append(f"duration {dur:.1f}s outside limits")
    if size > v["max_bytes"]:
        out.append(f"{size} bytes too large")
    if s.get("field_order") not in (None, "progressive", "unknown"):
        out.append("not progressive")
    for a in aus:
        if a["codec_name"] != v["audio_codec"] or int(a.get("channels", 2)) > 2:
            out.append("audio must be AAC mono/stereo")
    return out


def render(transcript_path: Path, out: Path, aspect: str = "square",
           variant: str | None = None) -> dict:
    t0 = time.monotonic()
    t = load_transcript(transcript_path)
    with tempfile.TemporaryDirectory() as td:
        webm = record(t, Path(td), aspect, variant)
        encode(webm, out, limits()["target"]["fps"])
    problems = validate(out)
    dur = float(probe(out)["format"]["duration"])
    lo, hi = limits()["target"]["duration_s"]
    if not lo <= dur <= hi:
        problems.append(f"duration {dur:.1f}s outside the 20-40 s target")
    return {"out": str(out), "seconds_to_render": round(time.monotonic() - t0, 1),
            "duration_s": round(dur, 1), "problems": problems}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--aspect", choices=["square", "wide"], default="square")
    ap.add_argument("--variant")
    a = ap.parse_args(argv)
    r = render(a.transcript, a.out, a.aspect, a.variant)
    print(json.dumps(r, indent=1))
    return 0 if not r["problems"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
