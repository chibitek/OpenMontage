#!/usr/bin/env python3
"""QA Test 10: Remotion render with a local, non-public asset.

Regression test for a bug where any Remotion composition fed a local
absolute-path asset (image or video living outside remotion-composer/public/,
e.g. anything under projects/<name>/assets/) failed at render time with:

    Error: Can only download URLs starting with http:// or https://, got
    "file:///..."

Remotion's Img/OffthreadVideo/Audio components only fetch over HTTP(S);
file:// URIs are rejected outright. The fix copies local assets into
remotion-composer/public/_local_assets/ and rewrites the path to be relative
before the composition ever sees it (VideoCompose._localize_local_assets).

This test hits the real `npx remotion render` CLI. First run pays Chrome
Headless Shell's download cost (cached thereafter). Skip unless
REMOTION_QA=1 is set so CI doesn't pay the cost on every run.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.video.video_compose import VideoCompose

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)

_SKIP_REASON = "Remotion QA is opt-in. Set REMOTION_QA=1 to render via the real npx remotion CLI."


def _runtime_ready() -> bool:
    composer_dir = Path(__file__).resolve().parent.parent.parent / "remotion-composer"
    return bool(shutil.which("npx")) and (composer_dir / "node_modules").exists()


def _make_fixture_clip(dest_dir: Path, name: str = "local_clip.mp4") -> Path:
    """Generate a real local mp4 with ffmpeg — deliberately NOT under
    remotion-composer/public/, to reproduce the reported bug."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / name
    if out.exists():
        return out
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=darkblue:s=640x360:d=3:r=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(out),
        ],
        capture_output=True, check=True, timeout=30,
    )
    return out


@pytest.mark.skipif(not os.environ.get("REMOTION_QA"), reason=_SKIP_REASON)
def test_cinematic_renderer_renders_local_absolute_path_asset(tmp_path: Path):
    if not _runtime_ready():
        pytest.skip("Remotion runtime not ready (npx + remotion-composer/node_modules).")

    clip = _make_fixture_clip(tmp_path / "assets_src")
    output_path = OUT / "remotion_local_asset_smoke.mp4"

    result = VideoCompose().execute({
        "operation": "remotion_render",
        "composition_data": {
            "renderer_family": "cinematic-trailer",
            "scenes": [
                {
                    "id": "s1",
                    "kind": "video",
                    "startSeconds": 0,
                    "durationSeconds": 3,
                    "src": str(clip),
                }
            ],
        },
        "output_path": str(output_path),
    })

    assert result.success, result.error
    assert output_path.exists()
    assert output_path.stat().st_size > 0

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
        capture_output=True, text=True, check=True,
    )
    duration = float(probe.stdout.strip())
    assert 2.5 < duration < 3.5, f"unexpected duration: {duration}"
