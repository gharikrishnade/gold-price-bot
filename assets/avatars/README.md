# Avatar portraits

Place portrait images used for talking-head (lip-synced) videos here, then point a
job at one via `avatar_image:` in `jobs.yaml` (with `video_style: avatar`).

Example (already wired for the Aries horoscope job):

```yaml
- { id: horoscope-aries, module: horoscope, channel: aries, language: hindi,
    formats: [long, short], video_style: avatar,
    avatar_image: assets/avatars/horoscope_sage.jpg, enabled: false }
```

## Add your image

Save your presenter portrait as:

```
assets/avatars/horoscope_sage.jpg
```

Tips for best lip-sync results:
- A clear, front-facing portrait with the full face visible.
- Even lighting, neutral/closed-mouth expression.
- The face reasonably large in the frame.

## How it's rendered

The pipeline generates the regional voiceover (Sarvam), then drives this image with
that audio via **SadTalker** (local, no per-video cost). The talking head is fitted to
the target canvas (1920×1080 for long, 1080×1920 for Shorts) with a blurred fill.

If SadTalker isn't configured/installed, the job automatically falls back to the
standard card (Ken Burns) video — nothing breaks. See the README "Talking-avatar
videos" section for SadTalker setup and the `SADTALKER_*` env vars.

> Note: image files in this folder are git-ignored by default (binary assets). Commit
> intentionally if you want the portrait tracked.
