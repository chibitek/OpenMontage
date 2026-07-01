"""Fast unit tests for local-asset handling in the Remotion render path.

Regression coverage for a latent bug: Remotion's Img/OffthreadVideo/Audio
components refuse `file://` URIs ("Can only download URLs starting with
http:// or https://"). `VideoCompose._remotion_render` used to convert local
absolute paths to `file://` URIs, and every composition's `resolveAsset()`
helper did the same as a fallback — both silently broken for any render that
fed a local asset living outside `remotion-composer/public/`. The fix: copy
local assets into `public/_local_assets/` and rewrite the path to be
relative, so `staticFile()` (the only mechanism Remotion's renderer actually
supports for local assets) can resolve it.

These tests do NOT invoke `npx remotion render` — that's covered by the
opt-in subprocess smoke test in tests/qa/test_10_remotion_local_assets.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools.video.video_compose import VideoCompose


# ------------------------------------------------------------------
# _localize_local_assets
# ------------------------------------------------------------------


def test_localize_passes_through_http_and_data_urls(tmp_path: Path):
    dest = tmp_path / "public" / "_local_assets"
    props = {
        "cuts": [
            {"source": "https://example.com/clip.mp4"},
            {"source": "http://example.com/clip.mp4"},
            {"source": "data:image/png;base64,AAAA"},
        ]
    }
    result = VideoCompose._localize_local_assets(props, dest)
    assert result["cuts"][0]["source"] == "https://example.com/clip.mp4"
    assert result["cuts"][1]["source"] == "http://example.com/clip.mp4"
    assert result["cuts"][2]["source"] == "data:image/png;base64,AAAA"
    assert not dest.exists()


def test_localize_leaves_plain_text_untouched(tmp_path: Path):
    """Non-path strings (titles, captions, etc.) must never be mistaken for assets."""
    dest = tmp_path / "public" / "_local_assets"
    props = {"title": "Hello World", "subtitle": "not/a/real/path.mp4"}
    result = VideoCompose._localize_local_assets(props, dest)
    assert result == props
    assert not dest.exists()


def test_localize_leaves_nonexistent_absolute_path_untouched(tmp_path: Path):
    dest = tmp_path / "public" / "_local_assets"
    missing = str(tmp_path / "does_not_exist.mp4")
    props = {"videoSrc": missing}
    result = VideoCompose._localize_local_assets(props, dest)
    assert result["videoSrc"] == missing
    assert not dest.exists()


def test_localize_copies_local_absolute_path_and_rewrites_relative(tmp_path: Path):
    src_dir = tmp_path / "assets"
    src_dir.mkdir()
    asset = src_dir / "clip.mp4"
    asset.write_bytes(b"fake-video-bytes")

    dest = tmp_path / "public" / "_local_assets"
    props = {"videoSrc": str(asset)}
    result = VideoCompose._localize_local_assets(props, dest)

    rewritten = result["videoSrc"]
    assert not rewritten.startswith("/")
    assert not rewritten.startswith("file://")
    assert rewritten.startswith("_local_assets/")
    assert rewritten.endswith("clip.mp4")

    copied = dest / Path(rewritten).name
    assert copied.exists()
    assert copied.read_bytes() == b"fake-video-bytes"


def test_localize_finds_paths_regardless_of_field_name_or_nesting(tmp_path: Path):
    """The bug wasn't specific to `cuts[].source` — every composition uses a
    different field name (videoSrc, scene.src, audio.narration.src, clip.src,
    backgroundSrc, ...). The localizer must walk the whole prop tree."""
    src_dir = tmp_path / "assets"
    src_dir.mkdir()
    image = src_dir / "bg.png"
    image.write_bytes(b"fake-image-bytes")

    dest = tmp_path / "public" / "_local_assets"
    props = {
        "scenes": [
            {"kind": "title", "backgroundSrc": str(image)},
        ],
        "audio": {"narration": {"src": str(image)}},
    }
    result = VideoCompose._localize_local_assets(props, dest)

    scene_src = result["scenes"][0]["backgroundSrc"]
    narration_src = result["audio"]["narration"]["src"]
    assert scene_src.startswith("_local_assets/")
    # Same source file referenced twice -> same content-addressed copy.
    assert scene_src == narration_src
    assert len(list(dest.iterdir())) == 1


def test_localize_strips_file_uri_prefix(tmp_path: Path):
    src_dir = tmp_path / "assets"
    src_dir.mkdir()
    asset = src_dir / "clip.mp4"
    asset.write_bytes(b"fake-video-bytes")

    dest = tmp_path / "public" / "_local_assets"
    props = {"videoSrc": f"file://{asset}"}
    result = VideoCompose._localize_local_assets(props, dest)
    assert result["videoSrc"].startswith("_local_assets/")
    assert (dest / Path(result["videoSrc"]).name).exists()


def test_localize_is_idempotent_across_calls(tmp_path: Path):
    """Repeated renders of the same asset must reuse the same copy, not
    duplicate it on every render."""
    src_dir = tmp_path / "assets"
    src_dir.mkdir()
    asset = src_dir / "clip.mp4"
    asset.write_bytes(b"fake-video-bytes")

    dest = tmp_path / "public" / "_local_assets"
    first = VideoCompose._localize_local_assets({"videoSrc": str(asset)}, dest)
    second = VideoCompose._localize_local_assets({"videoSrc": str(asset)}, dest)
    assert first["videoSrc"] == second["videoSrc"]
    assert len(list(dest.iterdir())) == 1


# ------------------------------------------------------------------
# Static regression checks — no composition should reintroduce file:// URIs
# ------------------------------------------------------------------

_REMOTION_SRC = Path(__file__).resolve().parent.parent.parent / "remotion-composer" / "src"


def test_no_composition_constructs_file_uris():
    """Regression: every resolveAsset() previously had a branch that built a
    `file:///...` URI for absolute paths. Remotion's renderer rejects those
    outright, so no .tsx file should construct one."""
    offenders = []
    for tsx in _REMOTION_SRC.rglob("*.tsx"):
        text = tsx.read_text(encoding="utf-8")
        if re.search(r"`file:///?\$\{", text) or "return `file://" in text:
            offenders.append(str(tsx))
    assert not offenders, f"file:// URI construction found in: {offenders}"


def test_talking_head_resolves_video_src_through_static_file():
    """TalkingHead.tsx used to pass videoSrc straight into OffthreadVideo with
    no resolution step at all — broken for any local absolute path."""
    text = (_REMOTION_SRC / "TalkingHead.tsx").read_text(encoding="utf-8")
    assert "resolveAsset" in text
    assert re.search(r"src=\{resolveAsset\(videoSrc\)\}", text)
