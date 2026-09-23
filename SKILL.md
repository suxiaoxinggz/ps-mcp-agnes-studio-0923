---
name: agnes-media-generation
description: Use only when the user explicitly mentions "agnes" (case-insensitive) and asks to generate, edit, combine, or animate images or videos with Agnes AI. Do not trigger for generic media generation without Agnes, media analysis, text generation, search, or live streaming.
---

# Agnes Media Generation

Use the `agnes_media` MCP server. If its tools are unavailable, ask the user to check the MCP configuration. Never activate without both the Agnes keyword and a media-generation intent.

## Models (2026-09)

- **Image**: `agnes-image-2.5-flash` (default, latest), `agnes-image-2.1-flash`, `agnes-image-2.0-flash`. All support tier `size` `1K`/`2K`/`3K`/`4K` + `ratio` (`1:1`,`3:4`,`4:3`,`16:9`,`9:16`,`2:3`,`3:2`,`21:9`); 2.0 also accepts legacy exact sizes (e.g. `1024x768`). Currently free.
- **Video**: `agnes-video-2.5-flash` (default, limited-time free, **720P only**, images≤5, audios≤3, no reference videos), `agnes-video-2.5` (paid: 720P $0.025/s, 1080P/1K $0.040/s, 2K $0.055/s), `agnes-video-v2.0` (legacy, 2.5-compatible).

## Workflow

1. Resolve the prompt language.
2. Select the narrowest matching tool.
3. Build a specific visual prompt and call the tool.
4. Present saved files and actionable errors.

## Tool selection

| Task | Tool | Key options |
|---|---|---|
| Standard image or image-to-image | `agnes_image_generate` | `size` tier (`1K`–`4K`) or exact pixels; `ratio`; optional `image_urls` |
| High-resolution image, wallpaper, poster | `agnes_image_generate_v2` | `size`=`1K`–`4K`; `ratio`; optional `image_urls` |
| Edit, restyle, or combine images | `agnes_image_edit` | One or more URL/local/Data-URI `image_paths` |
| Text-to-video | `agnes_video_generate` | `mode="text"`; `seconds` `"4"`–`"12"`; `size` `720P`/`1080P`/`1K`/`2K` (flash: `720P`) |
| First/last-frame video | `agnes_video_generate` | `mode="keyframe"`; `first_frame`/`last_frame` URLs (≥1 required) |
| Image/audio/video reference video | `agnes_video_generate` | `mode="reference"`; `images`/`audios`(/`videos` on 2.5); reference them as `<Picture 1>` etc. in the prompt |
| Async video or later polling | `agnes_video_submit` → `agnes_video_wait` / `agnes_video_status` | Preserve and report `video_id`; poll with `model_name` |

Defaults: image generation uses `agnes-image-2.5-flash`; for high-resolution use the tier `size` (`2K`/`4K`) with the requested `ratio`. Video generation uses `agnes-video-2.5-flash` (free) by default; switch to `agnes-video-2.5` via `AGNES_VIDEO_MODEL` only when the user accepts cost or needs 1080P/2K/reference videos.

## Video mode rules

- `text`: prompt only — no media fields.
- `keyframe`: `first_frame` and/or `last_frame` URLs required; no other media fields.
- `reference`: `images` and/or `audios` (2.5 also `videos`) required; no first/last frame. Reference media in the prompt as `<Picture 1>`, `<Audio 1>`, `<Video 1>`.
- `seconds` is a **string** `"4"`–`"12"`. `n` is always `1`. Flash rejects any `size` other than `"720P"` and any `videos` input (HTTP 400).

## Prompt language

Resolve the mode from the current request, then an explicit earlier preference, otherwise use `auto`:

- `auto`: translate non-English prompts into natural English and optimize silently.
- `original`: optimize without changing language when the user asks to preserve it.
- `review`: show original and English versions and wait for selection when requested.

Preserve intent, proper nouns, numbers, camera directions, and quoted/on-screen text. Use image prompts shaped as subject + scene + style + lighting + composition; video prompts as subject + action + camera + lighting (+ sound); image-edit prompts as change + keep-unchanged + target style.

## Constraints and recovery

- Image inputs accept public HTTPS URLs, Data URIs, and local paths; video inputs require public HTTPS URLs.
- Image generation may take seconds to tens of seconds — allow 60–360s timeouts. Video generation is async: submit, then poll every 1–2s with `video_id` + `model_name` until `completed`/`failed`.
- `response_format` must be placed inside `extra_body`; `return_base64` is top-level. Never send `tags: ["img2img"]`; never send `width`/`height`/`fps`/`num_frames` to video tools.
- Mask-based editing is unsupported.
- On 429 or 503, wait and retry. On timeout, report `video_id` so polling can continue. For other errors, report the returned code and message.

## Output

- Show every generated image inline from its absolute `local_paths` entry.
- For video, provide `local_path` and `video_url` when available.
- Do not expose credentials or invent a successful result when a tool returns an error.
