"""HeyGen digital-avatar video generation using a specific avatar_id/talking_photo_id + voice_id.

Generates a video of a HeyGen avatar (a "Look") speaking a script in a
chosen voice, via HeyGen's `/v2/video/generate` endpoint. This is distinct
from `heygen_video`, which routes through HeyGen's generic video-generation
gateway (VEO/Sora/Kling/etc.) and has no avatar_id/voice_id parameters at all.

Supports two voice-input modes:
- text: HeyGen's own TTS reads `script` in `voice_id` (original mode).
- audio: a pre-rendered audio file drives the avatar's lip sync instead of
  HeyGen's TTS. Pass `audio_path` (uploaded via HeyGen's asset endpoint) or
  an already-hosted `audio_url` directly. Lets narration be generated cheaply
  and iterated on locally (e.g. via `elevenlabs_tts` with a cloned voice)
  before spending HeyGen credits on the avatar render itself.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

_GENERATE_URL = "https://api.heygen.com/v2/video/generate"
_STATUS_URL = "https://api.heygen.com/v2/videos/{video_id}"
_ASSET_UPLOAD_URL = "https://upload.heygen.com/v1/asset"
_AUDIO_CONTENT_TYPES = {".mp3": "audio/mpeg", ".wav": "audio/wav"}


class HeyGenAvatar(BaseTool):
    name = "heygen_avatar"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "avatar"
    provider = "heygen"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:HEYGEN_API_KEY"]
    install_instructions = (
        "Set the HEYGEN_API_KEY environment variable:\n"
        "  export HEYGEN_API_KEY=your_key_here\n"
        "Get a key at https://app.heygen.com/settings/api\n"
        "Then find your avatar_id (\"Look ID\") and voice_id in the HeyGen "
        "studio (Avatars / Voices tabs), or via GET /v2/avatars and GET /v2/voices."
    )
    agent_skills = ["avatar-video"]
    fallback = "talking_head"
    fallback_tools = ["talking_head", "lip_sync"]

    capabilities = ["avatar_video", "digital_twin", "spokesperson_video"]
    supports = {
        "custom_avatar_id": True,
        "custom_voice_id": True,
        "captions": True,
        "test_mode": True,
    }
    best_for = [
        "spokesperson videos using a specific cloned/custom HeyGen avatar Look and Voice ID",
        "precise avatar_id + voice_id control (not generic prompt-to-video)",
    ]
    not_good_for = [
        "generic AI video generation without a specific avatar (use heygen_video or video_selector instead)",
        "offline/local rendering",
    ]

    input_schema = {
        "type": "object",
        "required": ["avatar_id"],
        "properties": {
            "script": {
                "type": "string",
                "description": "Text mode: text for the avatar to speak via HeyGen TTS. Required with voice_id if audio_path/audio_url are not given.",
            },
            "avatar_id": {
                "type": "string",
                "description": (
                    "HeyGen avatar/Look ID (character.avatar_id). Also accepts a "
                    "talking_photo_id when character_type='talking_photo'."
                ),
            },
            "voice_id": {
                "type": "string",
                "description": "Text mode: HeyGen voice_id. Required with script if audio_path/audio_url are not given.",
            },
            "audio_path": {
                "type": "string",
                "description": (
                    "Audio mode: local path to a pre-rendered narration file (mp3/wav, e.g. from "
                    "elevenlabs_tts with a cloned voice). Uploaded to HeyGen's asset endpoint and "
                    "used to drive lip sync directly, bypassing HeyGen's own TTS entirely."
                ),
            },
            "audio_url": {
                "type": "string",
                "description": "Audio mode: an already-hosted audio URL (skips the upload step). Takes precedence over audio_path if both are given.",
            },
            "character_type": {
                "type": "string",
                "enum": ["avatar", "talking_photo"],
                "default": "avatar",
                "description": (
                    "HeyGen character type. Most custom/cloned avatars (including "
                    "photo-avatar 'looks') use 'avatar'; use 'talking_photo' only if "
                    "avatar_id is actually a talking_photo_id."
                ),
            },
            "avatar_style": {
                "type": "string",
                "enum": ["normal", "closeUp", "circle"],
                "default": "normal",
            },
            "background_type": {
                "type": "string",
                "enum": ["color", "image", "video"],
                "default": "color",
            },
            "background_value": {
                "type": "string",
                "description": "Hex color when background_type='color'",
            },
            "background_url": {
                "type": "string",
                "description": "Image/video URL when background_type is 'image' or 'video'",
            },
            "width": {"type": "integer", "default": 1920},
            "height": {"type": "integer", "default": 1080},
            "speed": {"type": "number", "default": 1.0, "minimum": 0.5, "maximum": 2.0},
            "pitch": {"type": "number", "default": 0, "minimum": -20, "maximum": 20},
            "caption": {"type": "boolean", "default": False},
            "test": {
                "type": "boolean",
                "default": False,
                "description": "Watermarked, no-credit test mode for previewing before a real run",
            },
            "title": {"type": "string"},
            "output_path": {"type": "string"},
            "timeout_seconds": {"type": "integer", "default": 1200},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=500, network_required=True
    )
    retry_policy = RetryPolicy(
        max_retries=1, backoff_seconds=5.0, retryable_errors=["rate_limit", "timeout", "server_error"]
    )
    idempotency_key_fields = [
        "script", "avatar_id", "voice_id", "audio_path", "audio_url",
        "avatar_style", "background_type", "background_value",
    ]
    side_effects = [
        "writes video file to output_path",
        "calls HeyGen API",
        "consumes HeyGen account credits unless test=True",
    ]
    user_visible_verification = [
        "Watch the generated clip for lip-sync accuracy and natural avatar motion",
        "Confirm the avatar and voice match the intended Look ID and Voice ID",
    ]

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if os.environ.get("HEYGEN_API_KEY") else ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        # HeyGen bills via account credits, not a fixed per-call USD price.
        # This is a rough order-of-magnitude placeholder, not a real quote —
        # actual cost depends on the user's HeyGen plan and credit pricing.
        if inputs.get("test"):
            return 0.0
        if inputs.get("script"):
            return round(len(inputs["script"]) * 0.002, 4)
        # Audio mode: no script string to size off of — estimate from the
        # local audio file's duration when we can, else a flat placeholder.
        audio_path = inputs.get("audio_path")
        if audio_path and Path(audio_path).exists():
            duration = self._probe_audio_duration(audio_path)
            if duration:
                return round(duration * 0.03, 4)
        return 3.0

    @staticmethod
    def _probe_audio_duration(audio_path: str) -> float | None:
        import subprocess

        try:
            out = subprocess.check_output(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                text=True,
                timeout=15,
            )
            return float(out.strip())
        except Exception:
            return None

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 600.0  # HeyGen avatar videos typically take 5-15 minutes

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        import requests

        api_key = os.environ.get("HEYGEN_API_KEY")
        if not api_key:
            return ToolResult(success=False, error="HEYGEN_API_KEY not set. " + self.install_instructions)

        avatar_id = inputs["avatar_id"]
        character_type = inputs.get("character_type", "avatar")
        script = inputs.get("script")
        voice_id = inputs.get("voice_id")
        audio_path = inputs.get("audio_path")
        audio_url = inputs.get("audio_url")

        character: dict[str, Any] = {"type": character_type}
        if character_type == "talking_photo":
            character["talking_photo_id"] = avatar_id
        else:
            character["avatar_id"] = avatar_id
            character["avatar_style"] = inputs.get("avatar_style", "normal")

        if audio_url or audio_path:
            if not audio_url:
                if not Path(audio_path).exists():
                    return ToolResult(success=False, error=f"Audio file not found: {audio_path}")
                try:
                    audio_url = self._upload_audio_asset(audio_path, api_key)
                except Exception as exc:
                    return ToolResult(success=False, error=f"HeyGen audio asset upload failed: {exc}")
            voice: dict[str, Any] = {"type": "audio", "audio_url": audio_url}
        elif script and voice_id:
            voice = {
                "type": "text",
                "input_text": script,
                "voice_id": voice_id,
                "speed": inputs.get("speed", 1.0),
                "pitch": inputs.get("pitch", 0),
            }
        else:
            return ToolResult(
                success=False,
                error=(
                    "Provide either (audio_path or audio_url) for audio-driven mode, "
                    "or (script and voice_id) for HeyGen-TTS text mode."
                ),
            )

        background: dict[str, Any] = {"type": inputs.get("background_type", "color")}
        if background["type"] == "color":
            background["value"] = inputs.get("background_value", "#F1E6B2")
        else:
            background["url"] = inputs.get("background_url", "")

        payload: dict[str, Any] = {
            "video_inputs": [{"character": character, "voice": voice, "background": background}],
            "dimension": {"width": inputs.get("width", 1920), "height": inputs.get("height", 1080)},
            "caption": inputs.get("caption", False),
            "test": inputs.get("test", False),
        }
        if inputs.get("title"):
            payload["title"] = inputs["title"]

        start = time.time()
        try:
            body = self._generate_with_retry(payload, api_key)
        except Exception as exc:
            return ToolResult(success=False, error=f"HeyGen avatar video request failed: {exc}")

        if body.get("error"):
            return ToolResult(success=False, error=f"HeyGen API error: {body['error']}")

        video_id = (body.get("data") or {}).get("video_id")
        if not video_id:
            return ToolResult(success=False, error=f"No video_id in HeyGen response: {body}")

        timeout_seconds = inputs.get("timeout_seconds", 1200)
        try:
            video_url, clip_duration = self._poll(video_id, api_key, timeout_seconds)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc), data={"video_id": video_id})

        output_path = Path(inputs.get("output_path", f"heygen_avatar_{video_id}.mp4"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            download = requests.get(video_url, timeout=120)
            download.raise_for_status()
            output_path.write_bytes(download.content)
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Failed to download HeyGen video: {exc}",
                data={"video_id": video_id, "video_url": video_url},
            )

        return ToolResult(
            success=True,
            data={
                "provider": "heygen",
                "video_id": video_id,
                "avatar_id": avatar_id,
                "voice_mode": voice["type"],
                "voice_id": voice_id,
                "audio_url": audio_url,
                "character_type": character_type,
                "output": str(output_path),
                "format": "mp4",
                "test_mode": inputs.get("test", False),
                "clip_duration_seconds": clip_duration,
            },
            artifacts=[str(output_path)],
            duration_seconds=round(time.time() - start, 2),
            cost_usd=0.0 if inputs.get("test") else self.estimate_cost(inputs),
            model=f"heygen/{avatar_id}",
        )

    def _poll(self, video_id: str, api_key: str, timeout_seconds: int) -> tuple[str, float]:
        import requests

        deadline = time.time() + timeout_seconds
        interval = 5.0
        status_url = _STATUS_URL.format(video_id=video_id)

        while time.time() < deadline:
            response = requests.get(status_url, headers={"X-Api-Key": api_key}, timeout=30)
            response.raise_for_status()
            body = response.json()
            if body.get("error"):
                raise RuntimeError(f"HeyGen status error: {body['error']}")

            data = body.get("data") or {}
            status = data.get("status")

            if status == "completed":
                video_url = data.get("video_url")
                if not video_url:
                    raise RuntimeError(f"HeyGen video {video_id} completed but has no video_url")
                return video_url, float(data.get("duration") or 0.0)

            if status == "failed":
                raise RuntimeError(
                    "HeyGen video "
                    f"{video_id} failed: "
                    f"{data.get('failure_message', data.get('failure_code', 'unknown error'))}"
                )

            time.sleep(min(interval, max(0.0, deadline - time.time())))
            interval = min(interval * 1.2, 30.0)

        raise TimeoutError(f"HeyGen video {video_id} timed out after {timeout_seconds}s")

    @staticmethod
    def _generate_with_retry(payload: dict[str, Any], api_key: str, max_retries: int = 4) -> dict[str, Any]:
        """POST /v2/video/generate with exponential backoff on 429.

        Two distinct things return HTTP 429 from this endpoint:
        - A transient rolling-window rate limit — worth retrying with backoff.
        - `trial_video_limit_exceeded` — a hard daily quota of 5 requests,
          confirmed (2026-07-01) to apply specifically to `test: true` (free
          watermarked preview) calls, NOT to the account, plan, or API key as
          a whole. Real (`test: false`) generations succeed immediately even
          while this cap is active on test mode — verified directly against
          a Business-plan account where upgrading the plan and rotating the
          API key both had zero effect on the test-mode cap, but a real call
          on the very same (capped) key worked on the first try. No amount
          of backoff fixes the test-mode cap; it only resets on HeyGen's own
          daily window. Fail fast with a message that points at the real fix
          (retry with test: false) instead of burning through retries.
        """
        import requests

        backoff = 5.0
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    _GENERATE_URL,
                    headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=30,
                )
                if response.status_code == 429:
                    try:
                        err = response.json().get("error") or {}
                    except ValueError:
                        err = {}
                    if err.get("code") == "trial_video_limit_exceeded":
                        is_test = bool(payload.get("test"))
                        hint = (
                            "This cap has been confirmed to apply specifically to "
                            "test:true preview calls, not the account or plan — retry "
                            "the same request with test=False; it will very likely "
                            "succeed immediately (and will cost real credits)."
                            if is_test else
                            "This occurred on a test=False (real) call, which is "
                            "unexpected — the cap was previously only observed on "
                            "test:true calls. Re-verify before assuming this is the "
                            "same known issue."
                        )
                        raise RuntimeError(
                            "HeyGen daily trial video limit reached: "
                            f"{err.get('message', 'no message')} {hint}"
                        )
                    raise requests.HTTPError("429 rate limited", response=response)
                response.raise_for_status()
                return response.json()
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                last_exc = exc
                if status != 429 or attempt == max_retries:
                    raise
                time.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
            except Exception as exc:
                last_exc = exc
                raise
        raise last_exc  # pragma: no cover — loop always returns or raises

    @staticmethod
    def _upload_audio_asset(audio_path: str, api_key: str) -> str:
        """Upload a local audio file to HeyGen's asset endpoint, return its hosted URL.

        POST https://upload.heygen.com/v1/asset — raw binary body, Content-Type
        must match the file's MIME type. 10MB file-size limit per HeyGen's docs.
        """
        import requests

        path = Path(audio_path)
        content_type = _AUDIO_CONTENT_TYPES.get(path.suffix.lower())
        if not content_type:
            raise ValueError(
                f"Unsupported audio extension {path.suffix!r} for HeyGen upload. "
                f"Supported: {sorted(_AUDIO_CONTENT_TYPES)}"
            )
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > 10:
            raise ValueError(f"Audio file is {size_mb:.1f}MB — exceeds HeyGen's 10MB asset upload limit")

        response = requests.post(
            _ASSET_UPLOAD_URL,
            headers={"X-Api-Key": api_key, "Content-Type": content_type},
            data=path.read_bytes(),
            timeout=60,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("code") != 100:
            raise RuntimeError(body.get("message") or f"Upload failed: {body}")
        return body["data"]["url"]
