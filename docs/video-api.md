# Agnes Video API（2.5 / 2.5-flash / v2.0）

OpenAI Videos 兼容异步 API：先 `POST /v1/videos` 创建任务，再用 `video_id` + `model_name` 轮询。

- 创建：`POST https://apihub.agnes-ai.com/v1/videos`（国内站 `https://api.agnes-ai.cn/v1/videos`）
- 查询：`GET https://apihub.agnes-ai.com/agnesapi?video_id=<VIDEO_ID>&model_name=<MODEL>`
- 模型：`agnes-video-2.5`（收费）/ `agnes-video-2.5-flash`（限时免费，仅 720P）/ `agnes-video-v2.0`（旧版，接口兼容 2.5）

## 创建参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `model` | 是 | `agnes-video-2.5` / `agnes-video-2.5-flash` / `agnes-video-v2.0` |
| `prompt` | 是 | 主体+动作+镜头+风格(+声音)；reference 模式用 `<Picture N>` / `<Audio N>` / `<Video N>` 指代素材 |
| `mode` | 是 | `text`（纯文生视频）/ `keyframe`（首尾帧）/ `reference`（图/音/视频参考） |
| `seconds` | 否 | 字符串 `"4"`–`"12"`，默认 `"5"` |
| `size` | 否 | `720P` / `1080P` / `1K`(=1024x1024) / `2K`；**flash 仅 `720P`** |
| `aspect_ratio` | 否 | 默认 `16:9`；支持 `21:9` `16:9` `4:3` `1:1` `3:4` `9:16`（+`2:3` `3:2`），不支持 `auto` |
| `seed` | 否 | 整数 |
| `n` | 否 | 仅支持 `1` |

## 模式规则

| mode | 必需媒体 | 禁止字段 |
|---|---|---|
| text | 无 | first_frame / last_frame / images / audios / videos |
| keyframe | first_frame 与/或 last_frame | images / audios / videos |
| reference | images / audios / videos 至少一类 | first_frame / last_frame |

- `keyframe`：输入图保持为真实首/尾帧；`reference`：素材作为内容/风格/节奏参考，可能重新构图
- 参考视频对象：`{url, start_seconds, require_audio}`

## 媒体限制

| 媒体 | 2.5 | 2.5-flash |
|---|---|---|
| 图片 | ≤8 张，单张 <15MB，总计 <50MB，宽高 256–5760 | ≤5 张 |
| 音频 | ≤3 段，单段 <15MB，2–12s，总计 <64MB | ≤3 段 |
| 视频 | ≤1 个，2–12s，<50MB，24–60 FPS | ❌ 不支持（400） |

单次请求参考媒体总数 ≤12。

## 查询与响应

- 所有模式推荐：`GET /agnesapi?video_id=<ID>&model_name=<MODEL>`；不带 `model_name` 的查询仅适用 `mode: "text"`
- 状态：`queued` / `in_progress` / `completed` / `failed`；以 `status` 和顶层 `url` 为准（`internal_status`/`internal_progress` 是内部字段）
- 建议 1–2s 轮询；对 429/网络超时做退避重试，设置最大轮询时长

## Flash 专属校验（顺序：size → images → audios → videos）

- `size must be 720P`（其他值 400）
- `images length must not exceed 5`
- `audios length must not exceed 3`
- `videos is not supported`

## 尺寸映射

2.5：720P/1080P 按 ratio 映射（16:9 → 1280x720 / 1920x1080），1K 固定 1024x1024，2K 为 720P 的 2 倍。
2.5-flash（720P）：21:9→1680x720、16:9→1280x704、4:3→960x720、1:1→720x720、3:4→720x960、9:16→720x1280。

## 不支持的写法（400）

`video_url`/`video_path`/`video_reference`（用 `videos[].url`）；`input_reference`/`reference_url`；`width`/`height`/`fps`/`num_frames`/`quality`/`num_inference_steps`；`size` 写成像素（如 `1280x720`）；`aspect_ratio: "auto"`；`n != 1`。

## 计费

2.5：`视频总额 = (输出秒数 + 输入视频秒数) × 分辨率单价 + max(0, 图片数-5) × $0.005`；单价：720P $0.025/s、1080P/1K $0.040/s、2K $0.055/s。
2.5-flash：**限时 $0/s**（同公式，单价为 0）。示例：8s 720P 输出 + 3s 输入视频 + 7 张图 = (8+3)×$0.025 + 2×$0.005 = $0.285。
