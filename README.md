# Agnes Media MCP

![Python](https://img.shields.io/badge/python-3.11%2B-brightgreen.svg)
![MCP](https://img.shields.io/badge/MCP-Stdio-orange.svg)
![Image](https://img.shields.io/badge/Image-2.5%2F2.1%2F2.0--flash-blue.svg)
![Video](https://img.shields.io/badge/Video-2.5%2F2.5--flash%2Fv2.0-blue.svg)

> **2026-09 模型与视频 API 更新**：图片模型 `agnes-image-2.5-flash`（默认）/ `2.1-flash` / `2.0-flash`，均支持 `1K`–`4K` 档位 + `ratio`；视频 API 重写为 OpenAI Videos 兼容异步接口（`POST /v1/videos` → `GET /agnesapi?video_id=&model_name=`），模型 `agnes-video-2.5-flash`（限时免费）/ `agnes-video-2.5`（收费）/ `agnes-video-v2.0`。

---

## 这是什么？

一个 FastMCP Server，让 AI CLI（Claude Code / WorkBuddy / Codex / Qwen Code 等）直接调用 Agnes AI 的图片与视频生成能力：

- 🖼️ **文生图 / 图生图 / 多图合成**（三个 flash 图像模型，支持编辑、风格迁移、角色合成）
- 🎬 **文生视频 / 首尾帧控制 / 图·音·视频参考生成**（异步任务 + 自动轮询 + 本地下载）
- 💾 结果自动下载到本地（URL 之外落一份本地文件）
- 🔁 免费视频队列满（503）时的**后台重试脚本** `video_retry.py`

```
CLI 宿主 ──stdio──> Agnes Media MCP ──HTTPS──> apihub.agnes-ai.com（或 api.agnes-ai.cn）
                                                    ├─ /v1/images/generations   图片（同步）
                                                    ├─ /v1/videos               视频建任务（异步）
                                                    └─ /agnesapi?video_id=...   视频轮询
```

---

## 🧩 模型列表

### 图片模型（均免费，限时）

| 模型 | 特点 |
|---|---|
| `agnes-image-2.5-flash` | **最新一代（默认）**，综合能力全面超过 2.1；高信息密度、构图保留 |
| `agnes-image-2.1-flash` | 高信息密度、复杂构图；与 2.5 同 schema |
| `agnes-image-2.0-flash` | 高性能基线；图像编辑 ELO 1184（Top 20）；兼容历史精确尺寸 |

### 视频模型

| 模型 | 定价 | 限制 |
|---|---|---|
| `agnes-video-2.5-flash` | **限时 $0/s**（原价 720P $0.025/s） | **仅 720P**；参考图 ≤5；参考音频 ≤3；不支持参考视频 |
| `agnes-video-2.5` | 720P $0.025/s、1080P/1K $0.040/s、2K $0.055/s（按秒，输入视频秒数计入） | 参考图 ≤8（前 5 张免费）、参考视频 ≤1（2–12s）、参考音频 ≤3 |
| `agnes-video-v2.0` | 旧版模型，接口兼容 2.5 | 同 2.5 |

---

## 🛠 工具列表与支持参数

### 图片（3 个工具，同一 API：`POST /v1/images/generations`）

| 工具 | 默认模型 | 用途 |
|---|---|---|
| `agnes_image_generate` | `agnes-image-2.5-flash` | 文生图 / 图生图 / 多图合成（通用入口） |
| `agnes_image_generate_v2` | `agnes-image-2.5-flash` | 同上，默认使用**档位尺寸**（高分辨率/海报优先） |
| `agnes_image_edit` | `agnes-image-2.5-flash` | 编辑/合成入口（`image_paths` 支持 URL、Data URI、本地路径自动转 base64） |

**参数表**：

| 参数 | 必填 | 说明 |
|---|---|---|
| `prompt` | ✅ | ≤500 字。结构：[主体]+[场景]+[风格]+[光照]+[构图]+[质量]；编辑时写清"改什么+保留什么" |
| `size` | ✅ | 推荐 `1K`/`2K`/`3K`/`4K` 档位；兼容 `1024x768` 等历史精确尺寸（不支持的会被标准化） |
| `ratio` | — | 配合档位 `size`：`1:1` `3:4` `4:3` `16:9` `9:16` `2:3` `3:2` `21:9`（默认 `1:1`）。如 16:9 的 2K = `2624x1472` |
| `image_urls` | 图生图/多图必填 | 图片数组：公网 URL、Data URI Base64、**本地路径（自动转 base64）**；多图合成传多张 |
| `return_base64` | — | 顶层参数，文生图返回 base64 时使用 |
| `response_format` | — | `url` / `b64_json`——**必须放在 `extra_body` 内，顶层会报错** |
| `output_filename` / `extra_body` | — | 本地保存名 / 其他高级参数透传 |

⚠️ 图生图**不需要** `tags: ["img2img"]`；响应：`data[0].url` / `data[0].b64_json` / `data[0].revised_prompt`。

### 视频（4 个工具，异步 API）

| 工具 | 用途 |
|---|---|
| `agnes_video_submit` | 提交任务，返回 `video_id` + `task_id` |
| `agnes_video_status` | 按 `video_id` + `model_name` 查询状态/进度 |
| `agnes_video_wait` | 轮询直到完成/失败/超时，完成后自动下载 mp4 |
| `agnes_video_generate` | submit + wait 组合（一站式） |

**参数表**：

| 参数 | 必填 | 说明 |
|---|---|---|
| `prompt` | ✅ | 主体+动作+镜头+风格(+声音)；reference 模式用 `<Picture 1>` / `<Audio 1>` / `<Video 1>` 指代素材 |
| `mode` | ✅ | `text`（纯文生视频，禁止媒体字段）/ `keyframe`（首尾帧控制）/ `reference`（图/音/视频参考） |
| `seconds` | — | **字符串** `"4"`–`"12"`，默认 `"5"` |
| `size` | — | `720P` / `1080P` / `1K`（=1024x1024）/ `2K`；**flash 仅 `720P`** |
| `aspect_ratio` | — | `21:9` `16:9` `4:3` `1:1` `3:4` `9:16`（+`2:3` `3:2`），默认 `16:9`；不支持 `auto` 或像素写法 |
| `first_frame` / `last_frame` | keyframe | 首帧/尾帧图片 URL（至少一个） |
| `images` | reference | 参考图 URL 列表（2.5 ≤8 张，flash ≤5 张） |
| `audios` | reference | 参考音频 URL 列表（≤3 段，2–12s） |
| `videos` | reference（2.5） | 参考视频 `{url, start_seconds, require_audio}`（≤1 个，2–12s，<50MB，24–60FPS）；**flash 不支持** |
| `model_name` | status/wait | 轮询时指定模型（默认跟随配置）；不带 `model_name` 的裸查询仅适用 `mode:"text"` |

⚠️ `n` 仅支持 `1`；`width/height/fps/num_frames/quality` 等字段不受支持（会 400）；媒体 URL 必须公网可访问且在任务完成前有效。

---

## 🚀 安装与配置

```bash
git clone https://github.com/suxiaoxinggz/agnes-mcp-studio.git
cd agnes-mcp-studio
pip install -e .          # 或 uv sync
cp .env.example .env      # 填入 AGNES_API_KEY
```

`.env` 关键项（⚠️ `.cn` 与 `.com` 平台账号不互通，Key 不共用）：

```dotenv
AGNES_API_KEY=your-key
AGNES_BASE_URL=https://api.agnes-ai.cn/v1        # 国际站: https://apihub.agnes-ai.com/v1
AGNES_IMAGE_MODEL=agnes-image-2.5-flash          # 2.5 / 2.1 / 2.0-flash
AGNES_IMAGE_MODEL_V2=agnes-image-2.5-flash
AGNES_VIDEO_MODEL=agnes-video-2.5-flash          # 2.5-flash / 2.5 / v2.0
AGNES_OUTPUT_DIR=./outputs
```

MCP 客户端 JSON（所有支持 `mcpServers` 的宿主通用）：

```json
{
  "mcpServers": {
    "agnes-media": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/agnes-mcp-studio", "run", "agnes-media-mcp"],
      "env": { "AGNES_API_KEY": "<YOUR_KEY>", "AGNES_BASE_URL": "https://api.agnes-ai.cn/v1" }
    }
  }
}
```

### 免费视频队列满（503）？用后台重试

免费 `agnes-video-2.5-flash` 的队列经常满载（503 `video_queue_full`）。不要阻塞对话，用后台重试脚本：

```bash
cd agnes-mcp-studio
nohup python3 video_retry.py \
  --prompt "视频描述..." --seconds 5 --size 720P --aspect-ratio 16:9 --notify \
  > /tmp/agnes-video-retry.log 2>&1 &
```

- 每 `--interval` 秒（默认 600）重提一次，直到队列受理；随后自动轮询并下载 mp4 到 `outputs/videos/`
- 400/401/403 等不可重试错误会立即退出并写日志
- `--notify` 在出片时发 macOS 系统通知；日志在 `/tmp/agnes-video-retry.log`
- 想立即出片可切付费 `agnes-video-2.5`（5s 720P ≈ $0.125）——需你明确同意花费

---

## ✅ 验证结果（实测，2026-09）

| 测试 | 结果 |
|---|---|
| `agnes_image_generate`（2.5-flash，1024x1024，`response_format=url`） | ✅ 1024×1024 PNG 991KB（`outputs/images/`），`data[0].url` 正常返回 |
| Base URL 行为 | `.cn` 返回 401 时 `.com` 正常（Key 与站点必须匹配；两站账号不互通） |
| `agnes_video_generate`（2.5-flash） | ⚠️ 请求格式验证正确；免费队列满载期间服务端持续返回 503 `video_queue_full`（非参数错误），用 `video_retry.py` 等待空闲即可 |
| 7 个工具注册 | ✅ FastMCP 正常暴露 |

---

## 📁 项目结构

```
agnes-mcp-studio/
├── src/agnes_media_mcp/server.py   # FastMCP Server（7 个工具）
├── video_retry.py                  # 免费视频队列后台重试脚本
├── docs/image-api.md               # 图片 API 参考（3 模型 + 尺寸表 + 示例）
├── docs/video-api.md               # 视频 API 参考（模式规则 + 限制 + 计费）
├── docs/configuration.md           # 配置指南
├── SKILL.md                        # Agent Skill 指南（工具选择 / 模式规则 / 恢复策略）
├── .env.example                    # 环境变量模板
└── tests/
```

## 📄 License

见 [LICENSE](LICENSE)。API 服务与额度遵循 Agnes AI 平台协议；公开文档请统一使用 `YOUR_API_KEY` 占位，不要暴露真实密钥。
