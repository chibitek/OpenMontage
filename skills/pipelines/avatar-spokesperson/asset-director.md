# Asset Director - Avatar Spokesperson Pipeline

## When To Use

This stage prepares the actual spokesperson ingredients: narration, avatar or lip-sync footage, subtitle assets, branded backgrounds, and the minimal support graphics needed to complete the cut.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["scene_plan"]["scene_plan"]`, `state.artifacts["script"]["script"]`, `state.artifacts["idea"]["brief"]` | Presenter plan and narration needs |
| Tools | `talking_head`, `lip_sync`, `heygen_avatar`, `tts_selector`, `subtitle_gen`, `image_selector`, `audio_enhance` — selectors auto-discover all available providers from the registry | Avatar, narration, and support asset options |
| Playbook | Active style playbook | Background, type, and subtitle rules |

## Process

### 1. Lock The Avatar Generation Path

Use one primary path and record it clearly:

- `heygen_avatar` — a specific HeyGen avatar Look ID + Voice ID (the user's own cloned digital avatar). Best path when the user has HeyGen credentials for a real Look/Voice ID; produces the most natural, brand-consistent presenter. Two voice-input modes:
  - `voice.type: "text"` — HeyGen's own TTS reads the script. Simple, but pronunciation/pacing bugs (stutters, mispronunciations) can only be fixed by re-spending a full HeyGen render.
  - `voice.type: "audio"` (**preferred when an ElevenLabs (or other TTS) clone of the same voice exists**) — generate narration cheaply via `tts_selector`/`elevenlabs_tts` first, upload it via `heygen_avatar`'s `audio_path` input (this uploads to HeyGen's asset endpoint automatically and drives lip sync from that audio instead of HeyGen's TTS). Iterate on pacing/pronunciation almost for free before ever spending a HeyGen credit. See "Hybrid TTS→Avatar Workflow" below.
- `talking_head` from still image plus audio (SadTalker, local GPU),
- `lip_sync` from existing presenter plate plus new audio,
- externally supplied avatar render if created outside the current runtime.

Do not hide a blocked avatar path. Record it.

### 1a. Hybrid TTS→Avatar Workflow (heygen_avatar audio mode)

When the user has both a HeyGen avatar (Look ID) and a TTS voice clone of the same voice (e.g. ElevenLabs), prefer this over HeyGen's own TTS:

1. Generate narration with the cheap TTS tool (e.g. `elevenlabs_tts` with the user's `voice_id`). Iterate here — this costs cents, not credits.
2. Once the narration sounds right, pass the local audio file straight to `heygen_avatar` via `audio_path` (it uploads to `https://upload.heygen.com/v1/asset` and calls the avatar with `voice.type: "audio"` automatically — no separate upload step needed).
3. Only now do a HeyGen render (test mode first, see below).

If a script segment causes an avatar glitch (stutter, mispronunciation, unnatural pacing), the fix is almost always in the ElevenLabs step (rephrase, adjust `stability`/`style`, regenerate that segment's audio) — cheap to retry — rather than fighting HeyGen's own TTS.

### 1b. Sample Preview (Prevents Wasted Spend) — MANDATORY, no exceptions

Before **any** real (credit-consuming) HeyGen render, produce a `test: true` (free, watermarked) preview and confirm it first. This applies every time, not just the first generation of a project — re-verify after any script, voice, or framing change too.

1. **TTS sample** (if generating narration): Generate one section. Confirm voice, pace, and persona before batching the rest.
2. **Avatar sample** (`heygen_avatar` with `test: true`, or `talking_head`): Generate a short test clip. Confirm avatar quality, lip-sync, and pacing are acceptable before committing to a real render.

If rejected, adjust parameters and retry (max 3 iterations). Do not batch until approved. **Never call `heygen_avatar` with `test: false` without a preceding `test: true` call on the same (or materially similar) inputs.**

**Known exception (confirmed 2026-07-01):** HeyGen's free `test: true` preview has its own daily quota (observed: 5/day) that is entirely separate from the account's plan or credit balance — exhausting it returns HTTP 429 `trial_video_limit_exceeded`. This is NOT an account-wide block; do not spend time checking billing dashboards, upgrading plans, or rotating API keys over this specific error — none of those fix it. If the preview quota is exhausted and the scene has already been validated (script reviewed, prior scenes in the same project rendered cleanly with the same avatar/voice), it's acceptable to proceed directly to `test: false` for that scene rather than blocking the whole project on a quota reset. Tell the user this is what's happening.

### 1c. Scene-Level Regeneration, Not Whole-Script

When only part of an avatar render has an issue, regenerate just that scene/segment and stitch it back into the existing render — do not regenerate the full script end-to-end. Keep scenes as separate output files (e.g. `scene1.mp4`, `scene2.mp4`) precisely so a fix to one doesn't require paying for/re-rendering the others. After stitching, downstream caption/overlay timing must be rebuilt from the new stitched timeline's actual timestamps (re-transcribe), not reused from the old one.

### 2. Resolve Narration Before Support Graphics

Spokesperson videos depend on speech. Determine whether narration is:

- supplied,
- TTS-generated,
- already embedded in a presenter plate.

If narration is missing and no TTS tool is available, mark the project blocked instead of pretending the stage succeeded.

### 3. Build The Minimal Support Kit

Prepare only what the scene plan actually needs:

- subtitle files,
- one lower-third system,
- CTA card,
- background or plate assets,
- optional still or product support images.

### 4. Use Metadata For Capability Truth

Recommended metadata keys:

- `avatar_generation_path`
- `narration_assets`
- `subtitle_assets`
- `background_assets`
- `scene_asset_index`
- `blocked_assets`

### 5. Quality Gate

- the avatar path is explicit,
- narration and avatar assets align,
- support graphics stay minimal,
- every referenced file exists.

## No-Avatar Path

When the EP has triggered a narration-over-graphics pivot (neither `talking_head` nor `lip_sync` available), skip avatar generation entirely and produce a graphics-driven asset kit instead:

### What to produce:
1. **Narration audio** — via `tts_selector` (mandatory; block the project if no TTS is available either).
2. **Scene visuals** — via `image_selector` or `video_selector`. One primary visual per scene that reinforces the spoken point (diagram, illustration, product shot, or stock footage).
3. **Subtitle files** — same as standard path.
4. **Text cards** — key-point overlays, stat cards, CTA end card.
5. **Backgrounds** — consistent family matching the playbook.

### What to skip:
- No `talking_head` or `lip_sync` calls.
- No presenter framing metadata.
- `avatar_generation_path` should be set to `"none — narration-over-graphics pivot"`.

### Metadata for this path:
- `avatar_generation_path`: `"narration_over_graphics"`
- `pivot_reason`: why the no-avatar path was chosen
- All other metadata keys remain the same.

### Mid-Production Fact Verification

If you encounter uncertainty during asset generation:
- Use `web_search` to verify visual accuracy of subjects (e.g. what does this building actually look like?)
- Use `web_search` to find reference images before generating illustrations
- Log verification in the decision log: `category="visual_accuracy_check"`

Visual accuracy matters. If the script mentions a specific place, person, or object,
verify what it actually looks like before generating images. Don't rely on
the AI model's training data — it may be wrong or outdated.

## Common Pitfalls

- Building decorative assets before the narration path is solved.
- Mixing multiple avatar-generation strategies in one simple spokesperson video.
- Marking the stage complete when the core presenter asset is still hypothetical.
- (No-avatar path) Generating filler visuals with no connection to the narration — every image must reinforce the spoken point.


## When You Do Not Know How

If you encounter a generation technique, provider behavior, or prompting pattern you are unsure about:

1. **Search the web** for current best practices — models and APIs change frequently, and the agent's training data may be stale
2. **Check `.agents/skills/`** for existing Layer 3 knowledge (provider-specific prompting guides, API patterns)
3. **If neither helps**, write a project-scoped skill at `projects/<project-name>/skills/<name>.md` documenting what you learned
4. **Reference source URLs** in the skill so the knowledge is traceable
5. **Log it** in the decision log: `category: "capability_extension"`, `subject: "learned technique: <name>"`

This is especially important for:
- **Video generation prompting** — models respond to specific vocabularies that change with each version
- **Image model parameters** — optimal settings for FLUX, DALL-E, Imagen differ and evolve
- **Audio provider quirks** — voice cloning, music generation, and TTS each have model-specific best practices
- **Remotion component patterns** — new composition techniques emerge as the framework evolves

Do not rely on stale knowledge. When in doubt, search first.
