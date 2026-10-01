import shutil

import pytest

from lab import paths
from viz import render_video

SAMPLE = paths.ROOT / "viz/replay/samples/debate-sample.json"


def test_validation_rejects_out_of_spec(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg missing")
    import subprocess
    bad = tmp_path / "big.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=gray:s=1080x1080:d=1", "-pix_fmt", "yuv444p", "-c:v", "libx264",
                    str(bad)], check=True)
    problems = render_video.validate(bad)
    assert any("1080x1080" in p for p in problems)          # over X's 1024 height limit
    assert any("pixel format" in p for p in problems)


def test_renders_valid_mp4_under_two_minutes(tmp_path):
    pytest.importorskip("playwright")
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg missing")
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as pw:
            pw.chromium.launch().close()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"browser unavailable: {e}")
    r = render_video.render(SAMPLE, tmp_path / "case.mp4", "square")
    assert r["problems"] == [] and r["seconds_to_render"] < 120
    assert 20 <= r["duration_s"] <= 40
    info = render_video.probe(tmp_path / "case.mp4")
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (720, 720) and v["profile"] == "High"
