# Agnes Image API（2.5 / 2.1 / 2.0 Flash）

Endpoint：`POST https://apihub.agnes-ai.com/v1/images/generations`（国内站 `https://api.agnes-ai.cn/v1/images/generations`）

## 模型

| 模型 | 特点 | 定价 |
|---|---|---|
| `agnes-image-2.5-flash` | 最新一代，综合能力超过 2.1；高信息密度、构图保留 | 免费（限时） |
| `agnes-image-2.1-flash` | 高信息密度、复杂构图；与 2.5 同 schema | 免费（限时） |
| `agnes-image-2.0-flash` | 高性能基线；ELO 1184（图像编辑 Top 20） | 免费（限时） |

## 请求体

| 参数 | 必填 | 说明 |
|---|---|---|
| `model` | 是 | `agnes-image-2.5-flash` / `2.1-flash` / `2.0-flash` |
| `prompt` | 是 | ≤500 字；结构：[主体]+[场景]+[风格]+[光照]+[构图]+[质量] |
| `size` | 是 | 推荐 `1K`/`2K`/`3K`/`4K` 档位；兼容历史精确尺寸（如 `1024x768`，不支持的会被标准化） |
| `ratio` | 否 | 与档位 size 配合：`1:1` `3:4` `4:3` `16:9` `9:16` `2:3` `3:2` `21:9`（默认 1:1） |
| `return_base64` | 否 | 文生图返回 base64（顶层参数） |
| `extra_body.image` | 图生图/多图必填 | 图片数组：公网 URL 或 Data URI Base64（`data:image/png;base64,...`），多图合成传多张 |
| `extra_body.response_format` | 否 | `url` 或 `b64_json`——**必须放 extra_body 内，顶层会报错** |

⚠️ 图生图**不需要** `tags: ["img2img"]`；`response_format` 不要放顶层。

## 尺寸表（size 档位 × ratio）

| ratio | 1K | 2K | 3K | 4K |
|---|---|---|---|---|
| 1:1 | 1024x1024 | 2048x2048 | 3072x3072 | 4096x4096 |
| 3:4 | 864x1152 | 1728x2304 | 2592x3456 | 3456x4608 |
| 4:3 | 1152x864 | 2304x1728 | 3456x2592 | 4608x3456 |
| 16:9 | 1312x736 | 2624x1472 | 3936x2208 | 5248x2944 |
| 9:16 | 736x1312 | 1472x2624 | 2208x3936 | 2944x5248 |
| 2:3 | 832x1248 | 1664x2496 | 2496x3744 | 3328x4992 |
| 3:2 | 1248x832 | 2496x1664 | 3744x2496 | 4992x3328 |
| 21:9 | 1568x672 | 3136x1344 | 4704x2016 | 6272x2688 |

## 示例

文生图（URL 输出）：

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"agnes-image-2.5-flash","prompt":"...","size":"2K","ratio":"16:9","extra_body":{"response_format":"url"}}'
```

图生图（base64 输出）：

```bash
curl ... -d '{"model":"agnes-image-2.5-flash","prompt":"...","size":"1024x768","extra_body":{"image":["data:image/png;base64,BASE64_HERE"],"response_format":"b64_json"}}'
```

多图合成：`extra_body.image` 传多张 URL/base64，prompt 说明每张图的角色。

## 响应

`data[0].url` / `data[0].b64_json` / `data[0].revised_prompt`（三者互斥或 null）。

## 定价（当前限时免费）

刊例价：1K $0.010/张、2K $0.018/张、3K $0.021/张、4K $0.024/张；第 4 张起参考图 $0.003/张（前 3 张免费）。**当前全部 $0**。

## 超时

生成需数秒到数十秒，客户端超时建议 60–360s。
