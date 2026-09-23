# Agnes Media MCP

> **⚠️ 2026-09 Update**: The model list and video API have been overhauled (image `agnes-image-2.5-flash`/`2.1`/`2.0-flash` with 1K–4K tiers + ratio; async OpenAI-Videos-compatible API with `text`/`keyframe`/`reference` modes). This English README is pending re-translation — the up-to-date model list, parameter tables and deployment JSON are in [README.md](README.md) (Chinese) and `SKILL.md` / `docs/`.

[中文](README.md)

A FastMCP-based Agnes image and video generation MCP server (China edition).

> **China / International edition:** This documentation uses the China endpoint (`https://api.agnes-ai.cn/v1`). For the international edition, set `AGNES_BASE_URL` to `https://apihub.agnes-ai.com/v1`; request parameters and usage are otherwise essentially the same.
>
> ⚠️ **Important: Accounts are NOT shared between the two platforms, and API keys are NOT interchangeable.** A key issued on the China platform (`agnes-ai.cn`) will not work on the international endpoint, and vice versa. You must register and obtain a separate key on the respective platform.

This service reads credentials from environment variables. Do not commit real API keys to version control.

## What Is This?

This project consists of two parts, designed to be used **together**:

| Component | File | Role |
|-----------|------|------|
| **MCP Server** | `src/agnes_media_mcp/` | Execution layer — receives tool calls, requests the Agnes API, saves generated results |
| **Skill** | `SKILL.md` | Decision layer — tells the AI Agent when to activate, which tool to pick, how to craft prompts, and how to present results |

In short: **Skill is the brain, MCP is the hands**. Installing only MCP without the Skill means the Agent doesn't know when to call these tools; installing only the Skill without MCP means the Agent knows what to do but has no tools available.

## Workflow

<a href="docs/workflow.svg" target="_blank">
  <img src="docs/workflow.svg" alt="Agnes Media MCP Workflow" width="480" />
</a>

> Click the image to view full size

**Flow overview:**

```
User request ─→ [② Contains "agnes"?] ─No─→ Not activated, defer to other tools
                       │Yes
                       ▼
            ③ Intent matching (Skill: When to Use)
                       │
                       ▼
            ④ Decision rules → Select tool
             ├─ Standard image → agnes_image_generate
             ├─ High-resolution → agnes_image_generate_v2 (1K-4K + ratio)
             ├─ Image editing → agnes_image_edit
             └─ Video → agnes_video_generate / submit+wait
                       │
                       ▼
            ⑤ Craft prompt + language policy (auto / original / review)
                       │
                       ▼
            ⑥ MCP Server processing (payload / Base64 / 8n+1)
                       │
                       ▼
            ⑦ Agnes API (api.agnes-ai.cn/v1)
             ├─ Image: synchronous return b64_json / url
             └─ Video: video_id → poll GET /agnesapi
                       │
                       ▼
            ⑧ Save files → outputs/images/ | outputs/videos/
                       │
                       ▼
            ⑨ Agent presents results (Markdown / path / URL)
                       │
                       ▼
            ⑩ User receives media files
```

> The **Skill layer** (②③④⑤⑨) handles trigger detection, tool selection, prompt construction, and result presentation; the **MCP layer** (⑥⑧) handles protocol adaptation; the **API layer** (⑦) handles actual inference.

## Tool List

| Tool Name | Description |
|-----------|-------------|
| `agnes_image_generate` | Text-to-image / image-to-image (`agnes-image-2.1-flash`), exact pixel dimensions |
| `agnes_image_generate_v2` | High-information-density image generation (`agnes-image-2.1-flash`), tiered sizes `1K`–`4K` + aspect ratio |
| `agnes_image_edit` | Image editing / multi-image composition, reference images via `extra_body.image` |
| `agnes_video_submit` | Submit a video generation task (`POST /videos`), returns `video_id` |
| `agnes_video_status` | Query video task status (`GET /agnesapi?video_id=<VIDEO_ID>`) |
| `agnes_video_wait` | Poll task until completion, failure, or timeout |
| `agnes_video_generate` | Submit video task and wait for completion (submit + wait combo) |

## Full Installation Guide

> Prerequisite: [uv](https://docs.astral.sh/uv/) installed (one-line script, supports Windows / macOS / Linux).

### Step 1: Install the Skill

The Skill is a Markdown file that tells the AI Agent how to intelligently use these tools. Copy `SKILL.md` to your Agent's Skills directory:

**Hermes:**
```bash
# Clone the repository (or just download SKILL.md)
git clone https://github.com/Ryderey/agnes-mcp-studio

# Copy Skill to Hermes skills directory
cp agnes-mcp-studio/SKILL.md ~/.hermes/skills/agnes-media-generation.md
```

> 🪞 **Mirror:** If GitHub is unreachable, use the Gitee mirror instead: `git clone https://gitee.com/zzol_wow/agnes-mcp-studio` (identical content; apply the same substitution to all commands below).

**Qoder / Cursor / other Skill-capable clients:**

Copy `SKILL.md` to the corresponding Skills/Plugins directory, or import via the client's "Install Skill" feature.

### Step 2: Configure the MCP Server

Add the MCP server to your Agent's configuration file.

**Generic JSON format** (Claude Desktop / Cursor / Qoder):

```json
{
  "mcpServers": {
    "agnes_media": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/Ryderey/agnes-mcp-studio",
        "agnes-media-mcp"
      ],
      "env": {
        "AGNES_API_KEY": "your_agnes_api_key_here"
      }
    }
  }
}
```

> 🪞 **Mirror:** If GitHub is unreachable, replace `git+https://github.com/Ryderey/agnes-mcp-studio` with `git+https://gitee.com/zzol_wow/agnes-mcp-studio`.

**Hermes YAML format:**

```yaml
mcp_servers:
  agnes_media:
    command: "uvx"
    args:
      - "--from"
      - "git+https://github.com/Ryderey/agnes-mcp-studio"   # Mirror: git+https://gitee.com/zzol_wow/agnes-mcp-studio
      - "agnes-media-mcp"
    env:
      AGNES_API_KEY: "your_agnes_api_key_here"
      AGNES_OUTPUT_DIR: "/absolute/path/to/outputs"
    timeout: 600
    connect_timeout: 60
```

### Step 3: Obtain an API Key

1. Log in to the [Agnes AI Console](https://www.agnes-ai.cn) (China) or [agnes-ai.com](https://www.agnes-ai.com) (International) — accounts are separate
2. Navigate to the API Key management page, create and copy a key
3. Paste the key into the `AGNES_API_KEY` field from the previous step

### Step 4: Verify

Restart your Agent and confirm the MCP service is connected:

```bash
# Hermes
hermes mcp list
hermes mcp test agnes_media
```

Other clients typically show MCP connection status in their settings UI.

### Optional: Local Development Mode

If you want to modify the source code or debug:

```bash
git clone https://github.com/Ryderey/agnes-mcp-studio   # Mirror: git clone https://gitee.com/zzol_wow/agnes-mcp-studio
cd agnes-mcp-studio
uv sync
cp .env.example .env   # Edit .env and fill in your API Key
uv run agnes-media-mcp
```

### Optional: Pre-install Locally (Fast Startup)

`uvx --from git+...` clones the repository and installs dependencies on first launch, which can take tens of seconds. If your client has a short MCP connection timeout (e.g. WorkBuddy), pre-install locally instead:

```bash
# One-time install (use the gitee source in China, github source elsewhere)
uv tool install --from git+https://gitee.com/zzol_wow/agnes-mcp-studio agnes-media-mcp
```

The executable is installed to `~/.local/bin/agnes-media-mcp` (Windows: `%USERPROFILE%\.local\bin\agnes-media-mcp.exe`). Point your MCP config directly at it — startup then takes only ~2 seconds:

```json
{
  "mcpServers": {
    "agnes_media": {
      "command": "C:\\Users\\<username>\\.local\\bin\\agnes-media-mcp.exe",
      "args": [],
      "env": {
        "AGNES_API_KEY": "your_agnes_api_key_here"
      }
    }
  }
}
```

> On macOS / Linux, use the absolute path of `~/.local/bin/agnes-media-mcp` as `command`. To upgrade later, simply re-run the `uv tool install` command.

## Usage Examples

Once installed and configured, mention the **agnes** keyword in conversation to trigger. Here are real conversation examples:

### Prompt Language Policy

Before calling Agnes, the Skill translates non-English descriptions into natural English by default. This usually gives image and video models clearer style, camera, and composition instructions. Users can override the default in natural language at any time:

| Mode | How to select it | Behavior |
|------|------------------|----------|
| `auto` (default) | No instruction needed | Translate and optimize in English without asking |
| `original` | “Do not translate” or “keep the Chinese prompt” | Optimize the prompt while preserving its language |
| `review` | “Show me both versions first” | Show the original and English prompts, then wait for the user's choice |

An explicit preference remains active within the current conversation. Translation preserves proper nouns, numeric constraints, camera directions, and literal text that must appear in the result. It does not change the language used to communicate with the user.

### Generate an Image

> **You:** Use agnes to generate a cyberpunk cityscape at night, 16:9 wallpaper, 2K resolution
>
> **Agent:** Calls `agnes_image_generate_v2` (size=2K, ratio=16:9) → returns image file
>
> **You get:** A 2624×1472 image saved in the `outputs/images/` directory

### Edit an Image

> **You:** Use agnes to replace the background of this photo with a starry sky, keep the person unchanged [attached image]
>
> **Agent:** Calls `agnes_image_edit` (image_paths=[your image], prompt=...) → returns edited image

### Generate a Video

> **You:** Use agnes to make a 5-second video: a cat napping on a windowsill, sunlight slowly moving
>
> **Agent:** Calls `agnes_video_generate` (duration=5, resolution=720p) → waits 30s~3min → returns video file
>
> **You get:** An MP4 file saved in the `outputs/videos/` directory

### Trigger Rules

| What you say | Triggered? |
|--------------|------------|
| "Use agnes to draw a cat" | ✅ Triggered (contains agnes + image generation intent) |
| "Generate an image for me" | ❌ Not triggered (no mention of agnes) |
| "What is agnes?" | ❌ Not triggered (no generation intent) |
| "AGNES generate a wallpaper" | ✅ Triggered (case-insensitive) |

## Developer Reference

### Local Verification

```bash
uv run python -c "from agnes_media_mcp.server import mcp; print('import ok')"
uv run python -m pytest tests/ -v
```

### Direct Python API Calls

Programmatic usage examples without going through an Agent:

```python
import asyncio

from agnes_media_mcp.server import agnes_image_generate, agnes_image_generate_v2, agnes_video_generate

# Standard image generation
result = agnes_image_generate(
    prompt="A ceramic coffee mug on a steel table, soft lighting",
    size="1024x1024",
)

# High-resolution image generation
result = agnes_image_generate_v2(
    prompt="Cyberpunk cityscape at night, neon reflections, cinematic quality",
    size="2K",
    ratio="16:9",
)

# Video generation
result = asyncio.run(
    agnes_video_generate(
        prompt="Slow dolly-in shot, glass sculpture rotating in a gallery",
        duration=5,
        resolution="720p",
        aspect_ratio="16:9",
    )
)
```

> The prompt-language policy is implemented by the Skill. Direct Python API or MCP tool calls send `prompt` unchanged and do not translate it automatically.
>
> `agnes_video_wait` and `agnes_video_generate` may run for several minutes; use shorter timeouts when testing.

## Documentation

For detailed API documentation, see the `docs/` directory:

- [Image API Documentation](docs/image-api.md)
- [Video API Documentation](docs/video-api.md)

## Notes

- Default Base URL uses the China endpoint: `https://api.agnes-ai.cn/v1` (international: `https://apihub.agnes-ai.com/v1`)
- `response_format` must be placed inside `extra_body`, not at the top level of the request body
- Image-to-image does not use `tags: ["img2img"]`; reference images are passed via `extra_body.image`
- `agnes_image_generate_v2` uses `agnes-image-2.1-flash`, supporting `1K`–`4K` tiered sizes + `ratio` aspect ratio
- Video `num_frames` is automatically aligned to the `8n+1` rule (max 441)
- Video status polling uses `video_id` with endpoint `GET /agnesapi?video_id=<VIDEO_ID>`
- Video result URLs are extracted from the response's top-level `url` field (observed), with fallback to `metadata.url` (official docs)
- Successful responses expose normalized key fields without the full `raw` payload; HTTP errors retain the provider response body
- The `mask_path` parameter returns a structured unsupported error (mask functionality is not documented in the current API)
- Timeout responses include `video_id` and `last_response` for later polling

## License

[MIT License](LICENSE)
