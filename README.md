# Agnes Media MCP

> **2026-09 模型与视频 API 更新**：图片模型更新为 `agnes-image-2.5-flash`（默认）/ `2.1-flash` / `2.0-flash`，均支持 `1K`–`4K` 档位 + `ratio`（2.0 兼容历史精确尺寸）。视频 API 重写为 OpenAI Videos 兼容异步接口：`POST /v1/videos` 创建 → `GET /agnesapi?video_id=&model_name=` 轮询，模式 `text` / `keyframe` / `reference`，模型 `agnes-video-2.5-flash`（限时免费，仅 720P）/ `agnes-video-2.5`（收费）/ `agnes-video-v2.0`。最新参数以 `SKILL.md` 与 `docs/image-api.md`、`docs/video-api.md` 为准。

[English](README_EN.md)

基于 FastMCP 的 Agnes 图像与视频生成 MCP 服务器（国内版）。

> **国内版 / 国际版说明：** 本文档以国内版（`https://api.agnes-ai.cn/v1`）为例。国际版请将 `AGNES_BASE_URL` 设置为 `https://apihub.agnes-ai.com/v1`；请求参数和用法基本一致。
>
> ⚠️ **注意：两个平台的账号不互通，API Key 不共用。** 国内版 Key 无法在国际版端点使用，反之亦然。切换端点时必须在对应平台单独申请 Key。

本服务通过环境变量读取凭据，请勿将真实 API Key 放入版本控制文件。

## 这是什么？

本项目由两部分组成，**配套使用**：

| 组件 | 文件 | 作用 |
|------|------|------|
| **MCP Server** | `src/agnes_media_mcp/` | 执行层——接收工具调用，请求 Agnes API，保存生成结果 |
| **Skill** | `SKILL.md` | 决策层——告诉 AI Agent 何时激活、选哪个工具、如何构造 Prompt、如何展示结果 |

简单说：**Skill 是大脑，MCP 是双手**。只装 MCP 不装 Skill，Agent 不知道何时该调用这些工具；只装 Skill 不装 MCP，Agent 知道该做什么但没有工具可用。

## 工作流程

<a href="docs/workflow.svg" target="_blank">
  <img src="docs/workflow.svg" alt="Agnes Media MCP 工作流程" width="480" />
</a>

**流程概览：**

```
用户请求 ─→ [② 包含 "agnes"?] ─否─→ 不激活，交给其他工具
                    │是
                    ▼
         ③ 意图匹配 (Skill: When to Use)
                    │
                    ▼
         ④ 决策规则 → 选择工具
          ├─ 标准图像 → agnes_image_generate
          ├─ 高分辨率 → agnes_image_generate_v2 (1K-4K + ratio)
          ├─ 图像编辑 → agnes_image_edit
          └─ 视频     → agnes_video_generate / submit+wait
                    │
                    ▼
         ⑤ 构造 Prompt + 语言策略 (auto / original / review)
                    │
                    ▼
         ⑥ MCP Server 处理 (payload / Base64 / 8n+1)
                    │
                    ▼
         ⑦ Agnes API (api.agnes-ai.cn/v1)
          ├─ 图像: 同步返回 b64_json / url
          └─ 视频: video_id → 轮询 GET /agnesapi
                    │
                    ▼
         ⑧ 保存文件 → outputs/images/ | outputs/videos/
                    │
                    ▼
         ⑨ Agent 展示结果 (Markdown / 路径 / URL)
                    │
                    ▼
         ⑩ 用户获得媒体文件
```

> **Skill 层**（②③④⑤⑨）负责触发判断、工具选择、Prompt 构造和结果展示；**MCP 层**（⑥⑧）负责协议适配；**API 层**（⑦）负责实际推理。

## 工具列表

| 工具名 | 说明 |
|--------|------|
| `agnes_image_generate` | 文生图 / 图生图（`agnes-image-2.1-flash`），精确像素尺寸 |
| `agnes_image_generate_v2` | 高信息密度图像生成（`agnes-image-2.1-flash`），分级尺寸 `1K`–`4K` + 宽高比 |
| `agnes_image_edit` | 图像编辑 / 多图合成，通过 `extra_body.image` 传入参考图 |
| `agnes_video_submit` | 提交视频生成任务（`POST /videos`），返回 `video_id` |
| `agnes_video_status` | 查询视频任务状态（`GET /agnesapi?video_id=<VIDEO_ID>`） |
| `agnes_video_wait` | 轮询任务直至完成、失败或超时 |
| `agnes_video_generate` | 提交视频任务并等待完成（submit + wait 组合） |

## 完整安装配置指南

> 前提：已安装 [uv](https://docs.astral.sh/uv/)（一行脚本即可安装，支持 Windows / macOS / Linux）。

### 第一步：安装 Skill

Skill 是一个 Markdown 文件，告诉 AI Agent 如何智能地使用本工具。将 `SKILL.md` 复制到你的 Agent 的 Skills 目录：

**Hermes：**
```bash
# 克隆仓库（或仅下载 SKILL.md）
git clone https://github.com/Ryderey/agnes-mcp-studio

# 复制 Skill 到 Hermes skills 目录
cp agnes-mcp-studio/SKILL.md ~/.hermes/skills/agnes-media-generation.md
```

> 🇨🇳 **国内用户：** 若无法访问 GitHub，请改用 Gitee 镜像：`git clone https://gitee.com/zzol_wow/agnes-mcp-studio`（内容完全一致，后文配置命令同理替换）。

**Qoder / Cursor / 其他支持 Skill 的客户端：**

将 `SKILL.md` 复制到对应的 Skills/Plugins 目录，或通过客户端的「安装 Skill」功能导入。

### 第二步：配置 MCP Server

在你的 Agent 配置文件中添加 MCP 服务器。

**通用 JSON 格式**（Claude Desktop / Cursor / Qoder）：

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

> 🇨🇳 **国内用户：** 将 `git+https://github.com/Ryderey/agnes-mcp-studio` 替换为 `git+https://gitee.com/zzol_wow/agnes-mcp-studio` 即可。

**Hermes YAML 格式：**

```yaml
mcp_servers:
  agnes_media:
    command: "uvx"
    args:
      - "--from"
      - "git+https://github.com/Ryderey/agnes-mcp-studio"   # 国内用户替换为 git+https://gitee.com/zzol_wow/agnes-mcp-studio
      - "agnes-media-mcp"
    env:
      AGNES_API_KEY: "your_agnes_api_key_here"
      AGNES_OUTPUT_DIR: "/absolute/path/to/outputs"
    timeout: 600
    connect_timeout: 60
```

### 第三步：获取 API Key

1. 登录 [Agnes AI 控制台](https://www.agnes-ai.cn)
2. 进入 API Key 管理页面，创建并复制 Key
3. 将 Key 填入上一步配置中的 `AGNES_API_KEY`

### 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
|--------|:----:|--------|------|
| `AGNES_API_KEY` | 是 | — | Agnes AI 平台 API Key |
| `AGNES_BASE_URL` | 否 | `https://api.agnes-ai.cn/v1` | API 基础地址（国际版为 `https://apihub.agnes-ai.com/v1`） |
| `AGNES_IMAGE_MODEL` | 否 | `agnes-image-2.1-flash` | `agnes_image_generate` / `agnes_image_edit` 默认模型 |
| `AGNES_IMAGE_MODEL_V2` | 否 | `agnes-image-2.1-flash` | `agnes_image_generate_v2` 默认模型 |
| `AGNES_VIDEO_MODEL` | 否 | `agnes-video-v2.0` | 视频生成默认模型 |
| `AGNES_OUTPUT_DIR` | 否 | 源码树：`项目根/outputs`；安装后：`CWD/outputs` | 生成文件输出目录（建议配置绝对路径） |

本地开发模式也可将变量写入 `.env` 文件（参考 `.env.example`，启动时自动加载）。切换国内 / 国际端点时，必须同时更换为对应平台签发的 Key。

### 第四步：验证

重启 Agent 后，确认 MCP 服务已连接：

```bash
# Hermes
hermes mcp list
hermes mcp test agnes_media
```

其他客户端通常在设置界面可查看 MCP 连接状态。

### 可选：本地开发模式

如果你想修改源码或调试：

```bash
git clone https://github.com/Ryderey/agnes-mcp-studio   # 国内用户：git clone https://gitee.com/zzol_wow/agnes-mcp-studio
cd agnes-mcp-studio
uv sync
cp .env.example .env   # 编辑 .env 填入 API Key
uv run agnes-media-mcp
```

### 可选：预装到本地（快速启动）

`uvx --from git+...` 首次启动需克隆仓库并安装依赖，可能耗时数十秒；若你的客户端 MCP 连接超时较短（如 WorkBuddy），建议先预装到本地：

```bash
# 一次性安装（国内用 gitee 源，海外用 github 源）
uv tool install --from git+https://gitee.com/zzol_wow/agnes-mcp-studio agnes-media-mcp
```

安装后可执行文件位于 `~/.local/bin/agnes-media-mcp`（Windows：`%USERPROFILE%\.local\bin\agnes-media-mcp.exe`），MCP 配置直接指向它，启动仅需约 2 秒：

```json
{
  "mcpServers": {
    "agnes_media": {
      "command": "C:\\Users\\<用户名>\\.local\\bin\\agnes-media-mcp.exe",
      "args": [],
      "env": {
        "AGNES_API_KEY": "your_agnes_api_key_here"
      }
    }
  }
}
```

> macOS / Linux 将 `command` 换为 `~/.local/bin/agnes-media-mcp` 的绝对路径即可。后续升级只需重新执行 `uv tool install` 命令。

## 使用示例

安装配置完成后，在对话中提及 **agnes** 关键词即可触发。以下是实际对话示例：

### Prompt 语言策略

Skill 默认在调用 Agnes 前将非英文描述优化为自然英文；这通常能让图像和视频模型更稳定地理解风格、镜头与构图。用户可随时通过自然语言覆盖默认行为：

| 模式 | 如何选择 | 行为 |
|------|----------|------|
| `auto`（默认） | 无需说明 | 自动翻译并优化为英文，不额外询问 |
| `original` | “不要翻译”“保留中文提示词” | 优化提示词，但保持原语言 |
| `review` | “先给我中英文版本选择” | 展示原文和英文版，等待用户选择后再调用 |

同一对话中明确设置的偏好会继续沿用。翻译会保留专有名词、数值、镜头要求及必须出现在画面中的原文文字；Agent 与用户的交流语言不会因此改变。

### 生成图像

> **你：** 用 agnes 生成一张赛博朋克城市夜景，16:9 壁纸，2K 分辨率
>
> **Agent：** 调用 `agnes_image_generate_v2`（size=2K, ratio=16:9）→ 返回图片文件
>
> **你获得：** 一张 2624×1472 的图像，保存在 `outputs/images/` 目录

### 编辑图像

> **你：** 用 agnes 把这张照片的背景换成星空，保持人物不变 [附图]
>
> **Agent：** 调用 `agnes_image_edit`（image_paths=[你的图片], prompt=...）→ 返回编辑后的图片

### 生成视频

> **你：** 用 agnes 做一个 5 秒的视频：一只猫在窗台上打盹，阳光慢慢移动
>
> **Agent：** 调用 `agnes_video_generate`（duration=5, resolution=720p）→ 等待 30s~3min → 返回视频文件
>
> **你获得：** 一个 MP4 文件，保存在 `outputs/videos/` 目录

### 触发规则

| 你说的话 | 是否触发 |
|----------|----------|
| “用 agnes 画一只猫” | ✅ 触发（包含 agnes + 图像生成意图） |
| “帮我生成一张图片” | ❌ 不触发（未提及 agnes） |
| “agnes 是什么？” | ❌ 不触发（无生成意图） |
| “AGNES generate a wallpaper” | ✅ 触发（不区分大小写） |

## 开发者参考

### 本地验证

```bash
uv run python -c "from agnes_media_mcp.server import mcp; print('import ok')"
uv run python -m pytest tests/ -v
```

### Python API 直接调用

以下为无需通过 Agent 的编程调用示例：

```python
import asyncio

from agnes_media_mcp.server import agnes_image_generate, agnes_image_generate_v2, agnes_video_generate

# 标准图像生成
result = agnes_image_generate(
    prompt="一只陶瓷咖啡杯放在钢制桌面上，柔和光线",
    size="1024x1024",
)

# 高分辨率图像生成
result = agnes_image_generate_v2(
    prompt="赛博朋克城市夜景，霓虹灯反射，电影质感",
    size="2K",
    ratio="16:9",
)

# 视频生成
result = asyncio.run(
    agnes_video_generate(
        prompt="缓慢推进镜头，玻璃雕塑在画廊中旋转",
        duration=5,
        resolution="720p",
        aspect_ratio="16:9",
    )
)
```

> Prompt 语言策略由 Skill 层执行。直接调用 Python API 或 MCP 工具时，`prompt` 会按原样发送，不会自动翻译。
>
> `agnes_video_wait` 和 `agnes_video_generate` 可能运行数分钟，测试时建议使用较短超时。

## 文档

详细 API 文档请参阅 `docs/` 目录：

- [图像 API 文档](docs/image-api.md)
- [视频 API 文档](docs/video-api.md)
- [配置指南](docs/configuration.md)

## 注意事项

- Base URL 使用国内端点：`https://api.agnes-ai.cn/v1`
- `response_format` 必须放在 `extra_body` 内，不可置于请求体顶层
- 图生图不使用 `tags: ["img2img"]`，参考图通过 `extra_body.image` 传入
- `agnes_image_generate_v2` 使用 `agnes-image-2.1-flash`，支持 `1K`–`4K` 分级尺寸 + `ratio` 宽高比
- 视频 `num_frames` 自动对齐 `8n+1` 规则（上限 441）
- 视频状态轮询使用 `video_id`，端点为 `GET /agnesapi?video_id=<VIDEO_ID>`
- 视频结果 URL 从响应的顶层 `url` 字段提取（实测），同时兼容 `metadata.url`（官方文档示例）
- 成功响应仅返回归一化关键字段，不返回完整 `raw`；HTTP 错误仍保留服务端响应正文
- `mask_path` 参数会返回结构化不支持错误（当前文档未描述 mask 功能）
- 超时响应包含 `video_id` 和 `last_response`，可稍后继续轮询

## 许可证

[MIT License](LICENSE)
