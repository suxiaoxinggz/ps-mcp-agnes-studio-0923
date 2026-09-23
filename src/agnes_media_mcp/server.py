from __future__ import annotations

import asyncio
import base64
import math
import mimetypes
import os
import time
import uuid
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP


load_dotenv()

mcp = FastMCP("Agnes Media MCP")

DEFAULT_BASE_URL = "https://api.agnes-ai.cn/v1"
DEFAULT_IMAGE_MODEL = "agnes-image-2.5-flash"
DEFAULT_IMAGE_MODEL_V2 = "agnes-image-2.5-flash"
DEFAULT_VIDEO_MODEL = "agnes-video-2.5-flash"

SUPPORTED_IMAGE_MODELS = (
    "agnes-image-2.5-flash",   # 最新，免费
    "agnes-image-2.1-flash",   # 免费，与 2.5 同 schema
    "agnes-image-2.0-flash",   # 免费，兼容历史精确尺寸
)
SUPPORTED_VIDEO_MODELS = (
    "agnes-video-2.5-flash",   # 限时免费；仅 720P；images<=5；audios<=3；不支持参考视频
    "agnes-video-2.5",         # 收费：720P $0.025/s、1080P/1K $0.040/s、2K $0.055/s
    "agnes-video-v2.0",        # 旧版模型，接口兼容 2.5
)
VIDEO_SIZES = ("720P", "1080P", "1K", "2K")
VIDEO_ASPECT_RATIOS = ("21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "2:3", "3:2")
VIDEO_MODES = ("text", "keyframe", "reference")
# 可编辑源码树中锚定项目根；安装到 site-packages 时退化到 CWD
_src_root = Path(__file__).resolve().parent.parent.parent
if (_src_root / "pyproject.toml").exists():
    DEFAULT_OUTPUT_DIR = _src_root / "outputs"
else:
    DEFAULT_OUTPUT_DIR = Path.cwd() / "outputs"

VIDEO_URL_FIELDS = (
    "video_url",
    "url",
    "output_url",
    "result_url",
    "remixed_from_video_id",
)

_WINDOWS_RESERVED_STEMS = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CONIN$",
    "CONOUT$",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _base_url() -> str:
    return str(_env("AGNES_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")


def _domain_root() -> str:
    """Return scheme + host only, without any path prefix (e.g. /v1)."""
    parsed = urlparse(_base_url())
    return f"{parsed.scheme}://{parsed.netloc}"


def _image_model() -> str:
    return str(_env("AGNES_IMAGE_MODEL", DEFAULT_IMAGE_MODEL))


def _image_model_v2() -> str:
    return str(_env("AGNES_IMAGE_MODEL_V2", DEFAULT_IMAGE_MODEL_V2))


def _video_model() -> str:
    return str(_env("AGNES_VIDEO_MODEL", DEFAULT_VIDEO_MODEL))


def _error(
    code: str,
    message: str,
    *,
    details: Any | None = None,
    **extra: Any,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    result: dict[str, Any] = {"ok": False, "error": error}
    result.update(extra)
    return result


def _ensure_output_dir(kind: str) -> Path:
    root = Path(str(_env("AGNES_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)))).expanduser()
    directory = root / kind
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _sanitize_filename(filename: str | None) -> str | None:
    """Return a portable basename safe for use as output_filename."""
    if not filename:
        return None
    path = PureWindowsPath(filename)
    if path.drive or filename.startswith(("/", "\\")):
        return None
    name = path.name
    if (
        not name
        or name in {".", ".."}
        or name.endswith((" ", "."))
        or name.split(".", 1)[0].upper() in _WINDOWS_RESERVED_STEMS
    ):
        return None
    return name


def _request_json(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    timeout_seconds: float = 120.0,
    base_url: str | None = None,
) -> tuple[bool, dict[str, Any]]:
    api_key = _env("AGNES_API_KEY")
    if not api_key:
        return False, _error(
            "missing_api_key",
            "Set AGNES_API_KEY in the environment before calling Agnes.",
        )

    url = f"{base_url or _base_url()}{path}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.request(method, url, headers=headers, json=json_body)
            response.raise_for_status()
            if not response.content:
                return True, {}
            return True, response.json()
    except httpx.HTTPStatusError as exc:
        return False, _error(
            "http_error",
            "Agnes returned a non-success HTTP response.",
            details={
                "status_code": exc.response.status_code,
                "body": _response_body(exc.response),
            },
        )
    except httpx.TimeoutException as exc:
        return False, _error(
            "timeout",
            "The request to Agnes timed out.",
            details={"exception": str(exc)},
        )
    except httpx.RequestError as exc:
        return False, _error(
            "request_error",
            "The request to Agnes could not be completed.",
            details={"exception": str(exc)},
        )
    except ValueError as exc:
        return False, _error(
            "invalid_response",
            "Agnes returned a response that was not valid JSON.",
            details={"exception": str(exc)},
        )


def _response_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _is_remote_or_data_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https", "data"}


def _path_to_data_url(path_value: str) -> tuple[bool, str | dict[str, Any]]:
    path = Path(path_value).expanduser()
    if not path.exists():
        return False, _error(
            "file_not_found",
            "Local image path does not exist.",
            details={"path": str(path)},
        )
    if not path.is_file():
        return False, _error(
            "invalid_file",
            "Local image path is not a file.",
            details={"path": str(path)},
        )

    mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError as exc:
        return False, _error(
            "file_read_error",
            "Could not read local image path.",
            details={"path": str(path), "exception": str(exc)},
        )
    return True, f"data:{mime_type};base64,{encoded}"


def _normalize_image_inputs(values: list[str] | None) -> tuple[bool, list[str] | dict[str, Any]]:
    normalized: list[str] = []
    for value in values or []:
        if _is_remote_or_data_url(value):
            normalized.append(value)
            continue
        ok, data_url_or_error = _path_to_data_url(value)
        if not ok:
            return False, data_url_or_error
        normalized.append(str(data_url_or_error))
    return True, normalized


def _build_image_payload(
    *,
    prompt: str,
    model: str,
    size: str | None = None,
    ratio: str | None = None,
    return_base64: bool | None = None,
    response_format: str | None = None,
    image_urls: list[str] | None = None,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": model, "prompt": prompt}
    if size:
        payload["size"] = size
    if ratio:
        payload["ratio"] = ratio
    if return_base64 is not None:
        payload["return_base64"] = return_base64

    merged_extra_body = dict(extra_body or {})
    if response_format:
        merged_extra_body["response_format"] = response_format
    if image_urls:
        merged_extra_body["image"] = image_urls
    if merged_extra_body:
        payload["extra_body"] = merged_extra_body

    return payload


def _image_entries(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]

    entries: list[dict[str, Any]] = []
    for key in ("url", "b64_json", "image_url"):
        value = response.get(key)
        if isinstance(value, str):
            entries.append({key: value})
    return entries


def _safe_name(prefix: str, suffix: str, index: int | None = None) -> str:
    stem = f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    if index is not None:
        stem = f"{stem}-{index + 1}"
    return f"{stem}{suffix}"


def _suffix_from_url_or_content_type(
    url: str,
    content_type: str | None,
    default_suffix: str,
) -> str:
    suffix = Path(urlparse(url).path).suffix
    if suffix:
        return suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return guessed
    return default_suffix


def _save_data_url(data_url: str, directory: Path, filename: str | None, index: int) -> str:
    header, encoded = data_url.split(",", 1)
    content_type = header[5:].split(";", 1)[0] if header.startswith("data:") else None
    suffix = mimetypes.guess_extension(content_type or "") or ".bin"
    path = directory / (filename or _safe_name("agnes-image", suffix, index))
    path.write_bytes(base64.b64decode(encoded))
    return str(path)


def _save_b64_image(
    encoded: str,
    directory: Path,
    filename: str | None,
    index: int,
) -> str:
    if encoded.startswith("data:"):
        return _save_data_url(encoded, directory, filename, index)
    path = directory / (filename or _safe_name("agnes-image", ".png", index))
    path.write_bytes(base64.b64decode(encoded))
    return str(path)


def _download_url(
    url: str,
    directory: Path,
    *,
    filename: str | None = None,
    default_suffix: str,
    timeout_seconds: float = 180.0,
) -> tuple[bool, str | dict[str, Any]]:
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            suffix = _suffix_from_url_or_content_type(
                url,
                response.headers.get("content-type"),
                default_suffix,
            )
            path = directory / (filename or _safe_name("agnes-media", suffix))
            path.write_bytes(response.content)
            return True, str(path)
    except httpx.HTTPStatusError as exc:
        return False, _error(
            "download_http_error",
            "The generated asset URL returned a non-success HTTP response.",
            details={"status_code": exc.response.status_code, "url": url},
        )
    except httpx.RequestError as exc:
        return False, _error(
            "download_error",
            "The generated asset URL could not be downloaded.",
            details={"url": url, "exception": str(exc)},
        )
    except OSError as exc:
        return False, _error(
            "file_write_error",
            "The generated asset could not be written to disk.",
            details={"url": url, "exception": str(exc)},
        )
    except (ValueError, base64.binascii.Error) as exc:
        return False, _error(
            "decode_error",
            "The generated asset data could not be decoded.",
            details={"url": url, "exception": str(exc)},
        )


def _persist_images(
    response: dict[str, Any],
    *,
    output_filename: str | None = None,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    directory = _ensure_output_dir("images")
    urls: list[str] = []
    local_paths: list[str] = []
    save_errors: list[dict[str, Any]] = []

    for index, entry in enumerate(_image_entries(response)):
        url = entry.get("url") or entry.get("image_url")
        b64_json = entry.get("b64_json")
        if isinstance(url, str):
            if url.startswith("data:"):
                try:
                    local_paths.append(_save_data_url(url, directory, output_filename, index))
                except (ValueError, OSError, base64.binascii.Error) as exc:
                    save_errors.append(
                        _error(
                            "save_error",
                            "Could not save generated image data URL.",
                            details={"exception": str(exc)},
                        )["error"]
                    )
            else:
                urls.append(url)
                ok, path_or_error = _download_url(
                    url,
                    directory,
                    filename=output_filename,
                    default_suffix=".png",
                )
                if ok:
                    local_paths.append(str(path_or_error))
                else:
                    save_errors.append(path_or_error["error"])  # type: ignore[index]
        elif isinstance(b64_json, str):
            try:
                local_paths.append(_save_b64_image(b64_json, directory, output_filename, index))
            except (ValueError, OSError, base64.binascii.Error) as exc:
                save_errors.append(
                    _error(
                        "save_error",
                        "Could not save generated image base64 data.",
                        details={"exception": str(exc)},
                    )["error"]
                )

    return urls, local_paths, save_errors


def _agnes_image_generate_impl(
    prompt: str,
    *,
    model: str | None = None,
    size: str = "1024x1024",
    ratio: str | None = None,
    return_base64: bool | None = None,
    response_format: str | None = None,
    image_urls: list[str] | None = None,
    output_filename: str | None = None,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not prompt.strip():
        return _error("invalid_prompt", "Prompt must not be empty.")

    output_filename = _sanitize_filename(output_filename)

    ok, normalized_or_error = _normalize_image_inputs(image_urls)
    if not ok:
        return normalized_or_error  # type: ignore[return-value]

    payload = _build_image_payload(
        prompt=prompt,
        model=model or _image_model(),
        size=size,
        ratio=ratio,
        return_base64=return_base64,
        response_format=response_format,
        image_urls=normalized_or_error,  # type: ignore[arg-type]
        extra_body=extra_body,
    )
    ok, response = _request_json("POST", "/images/generations", json_body=payload)
    if not ok:
        return response

    image_urls_out, local_paths, save_errors = _persist_images(
        response,
        output_filename=output_filename,
    )
    return {
        "ok": True,
        "model": payload["model"],
        "image_urls": image_urls_out,
        "local_paths": local_paths,
        "save_errors": save_errors,
    }


def _agnes_image_edit_impl(
    prompt: str,
    image_paths: list[str],
    *,
    model: str | None = None,
    mask_path: str | None = None,
    size: str = "1024x1024",
    ratio: str | None = None,
    return_base64: bool | None = None,
    response_format: str | None = None,
    output_filename: str | None = None,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if mask_path:
        return _error(
            "unsupported_parameter",
            "mask_path is not supported by the confirmed Agnes image API.",
            details={
                "parameter": "mask_path",
                "reason": "The documented image edit flow uses img2img via extra_body.image.",
            },
        )
    if not image_paths:
        return _error(
            "missing_image",
            "At least one image URL or local image path is required for image edit.",
        )
    return _agnes_image_generate_impl(
        prompt,
        model=model,
        size=size,
        ratio=ratio,
        return_base64=return_base64,
        response_format=response_format,
        image_urls=image_paths,
        output_filename=output_filename,
        extra_body=extra_body,
    )


def _even(value: float) -> int:
    return max(2, int(round(value / 2.0) * 2))


def _parse_aspect_ratio(aspect_ratio: str) -> tuple[float, float]:
    if ":" not in aspect_ratio:
        raise ValueError("aspect_ratio must look like '16:9', '9:16', or '1:1'.")
    width_value, height_value = aspect_ratio.split(":", 1)
    width = float(width_value)
    height = float(height_value)
    if width <= 0 or height <= 0:
        raise ValueError("aspect_ratio values must be greater than zero.")
    return width, height


def _parse_dimensions(resolution: str, aspect_ratio: str) -> tuple[int, int]:
    normalized_resolution = resolution.lower().strip()
    if "x" in normalized_resolution:
        width_value, height_value = normalized_resolution.split("x", 1)
        width = int(width_value)
        height = int(height_value)
        if width <= 0 or height <= 0:
            raise ValueError("resolution dimensions must be greater than zero.")
        return _even(width), _even(height)

    if normalized_resolution.endswith("p"):
        short_side = int(normalized_resolution[:-1])
    else:
        short_side = int(normalized_resolution)
    if short_side <= 0:
        raise ValueError("resolution must be greater than zero.")

    ratio_width, ratio_height = _parse_aspect_ratio(aspect_ratio)
    if ratio_width >= ratio_height:
        height = short_side
        width = short_side * ratio_width / ratio_height
    else:
        width = short_side
        height = short_side * ratio_height / ratio_width
    return _even(width), _even(height)


def _align_num_frames(raw_frames: int) -> int:
    """Align frame count to the 8n+1 rule with a maximum of 441."""
    clamped = min(max(1, raw_frames), 441)
    # Find the nearest 8n+1 value: 1, 9, 17, ..., 441
    n = round((clamped - 1) / 8.0)
    aligned = 8 * n + 1
    return min(max(1, aligned), 441)




def _validate_video_request(
    *,
    model: str,
    mode: str,
    size: str,
    seconds: str,
    aspect_ratio: str,
    first_frame: str | None,
    last_frame: str | None,
    images: list[str] | None,
    audios: list[str] | None,
    videos: list[dict[str, Any]] | None,
) -> str | None:
    """Return an error message when the request violates Agnes video rules."""
    if mode not in VIDEO_MODES:
        return f"mode must be one of {'/'.join(VIDEO_MODES)}."
    if seconds and (not seconds.isdigit() or not 4 <= int(seconds) <= 12):
        return "seconds must be a numeric string between '4' and '12'."
    if aspect_ratio not in VIDEO_ASPECT_RATIOS:
        return f"aspect_ratio must be one of {'/'.join(VIDEO_ASPECT_RATIOS)}."
    if model.startswith("agnes-video-2.5-flash"):
        if size != "720P":
            return "agnes-video-2.5-flash only supports size '720P'."
        if videos:
            return "agnes-video-2.5-flash does not support reference videos."
        if images and len(images) > 5:
            return "agnes-video-2.5-flash supports at most 5 reference images."
        if audios and len(audios) > 3:
            return "agnes-video-2.5-flash supports at most 3 reference audios."
    else:
        if size not in VIDEO_SIZES:
            return f"size must be one of {'/'.join(VIDEO_SIZES)}."
        if images and len(images) > 8:
            return "At most 8 reference images are allowed."
        if videos and len(videos) > 1:
            return "At most 1 reference video is allowed."
    media_fields = (bool(first_frame or last_frame), bool(images), bool(audios), bool(videos))
    if mode == "text" and any(media_fields):
        return "mode='text' must not include first_frame/last_frame/images/audios/videos."
    if mode == "keyframe":
        if not (first_frame or last_frame):
            return "mode='keyframe' requires first_frame or last_frame."
        if images or audios or videos:
            return "mode='keyframe' must not include images/audios/videos."
    if mode == "reference":
        if first_frame or last_frame:
            return "mode='reference' must not include first_frame/last_frame."
        if not (images or audios or videos):
            return "mode='reference' requires images, audios, or videos."
    return None


def _build_video_payload(
    *,
    prompt: str,
    model: str,
    mode: str = "text",
    seconds: str = "5",
    size: str = "720P",
    aspect_ratio: str = "16:9",
    seed: int | None = None,
    first_frame: str | None = None,
    last_frame: str | None = None,
    images: list[str] | None = None,
    audios: list[str] | None = None,
    videos: list[dict[str, Any]] | None = None,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "mode": mode,
        "seconds": seconds,
        "size": size,
        "aspect_ratio": aspect_ratio,
    }
    if seed is not None:
        payload["seed"] = seed
    if mode == "keyframe":
        if first_frame:
            payload["first_frame"] = first_frame
        if last_frame:
            payload["last_frame"] = last_frame
    if mode == "reference":
        if images:
            payload["images"] = images
        if audios:
            payload["audios"] = audios
        if videos:
            payload["videos"] = videos
    if extra_body:
        payload["extra_body"] = dict(extra_body)
    return payload


def _extract_task_id(response: dict[str, Any]) -> str | None:
    for key in ("task_id", "id"):
        value = response.get(key)
        if isinstance(value, str) and value:
            return value

    data = response.get("data")
    if isinstance(data, dict):
        return _extract_task_id(data)
    return None


def _extract_video_id(response: dict[str, Any]) -> str | None:
    value = response.get("video_id")
    if isinstance(value, str) and value:
        return value

    data = response.get("data")
    if isinstance(data, dict):
        return _extract_video_id(data)
    return None


def _extract_status(response: dict[str, Any]) -> str | None:
    status = response.get("status")
    if isinstance(status, str):
        return status
    data = response.get("data")
    if isinstance(data, dict):
        return _extract_status(data)
    return None


def _looks_like_url(value: str) -> bool:
    return urlparse(value).scheme in {"http", "https"}


def _extract_video_url(response: dict[str, Any]) -> str | None:
    # Check metadata.url first (some responses use this location)
    metadata = response.get("metadata")
    if isinstance(metadata, dict):
        meta_url = metadata.get("url")
        if isinstance(meta_url, str) and _looks_like_url(meta_url):
            return meta_url

    for key in VIDEO_URL_FIELDS:
        value = response.get(key)
        if isinstance(value, str) and _looks_like_url(value):
            return value

    data = response.get("data")
    if isinstance(data, dict):
        return _extract_video_url(data)
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                value = _extract_video_url(item)
                if value:
                    return value
    return None


def _video_success_result(
    response: dict[str, Any],
    *,
    fallback_video_id: str | None = None,
    include_raw: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "task_id": _extract_task_id(response) or fallback_video_id,
        "video_id": _extract_video_id(response) or fallback_video_id,
        "status": _extract_status(response),
        "video_url": _extract_video_url(response),
    }
    for field in ("model", "progress", "seconds", "size", "created_at", "completed_at"):
        value = response.get(field)
        if value is not None:
            result[field] = value
    if response.get("error") is not None:
        result["task_error"] = response["error"]
    if include_raw:
        result["raw"] = response
    return result


def _agnes_video_submit_impl(
    prompt: str,
    *,
    model: str | None = None,
    mode: str = "text",
    seconds: str = "5",
    size: str = "720P",
    aspect_ratio: str = "16:9",
    seed: int | None = None,
    first_frame: str | None = None,
    last_frame: str | None = None,
    images: list[str] | None = None,
    audios: list[str] | None = None,
    videos: list[dict[str, Any]] | None = None,
    extra_body: dict[str, Any] | None = None,
    include_raw: bool = False,
) -> dict[str, Any]:
    if not prompt.strip():
        return _error("invalid_prompt", "Prompt must not be empty.")

    model = model or _video_model()
    error_message = _validate_video_request(
        model=model,
        mode=mode,
        size=size,
        seconds=seconds,
        aspect_ratio=aspect_ratio,
        first_frame=first_frame,
        last_frame=last_frame,
        images=images,
        audios=audios,
        videos=videos,
    )
    if error_message:
        return _error("invalid_video_options", error_message)

    payload = _build_video_payload(
        prompt=prompt,
        model=model,
        mode=mode,
        seconds=seconds,
        size=size,
        aspect_ratio=aspect_ratio,
        seed=seed,
        first_frame=first_frame,
        last_frame=last_frame,
        images=images,
        audios=audios,
        videos=videos,
        extra_body=extra_body,
    )

    ok, response = _request_json("POST", "/videos", json_body=payload)
    if not ok:
        return response

    return _video_success_result(response, include_raw=include_raw)


def _agnes_video_status_impl(
    video_id: str,
    *,
    model_name: str | None = None,
    include_raw: bool = False,
) -> dict[str, Any]:
    if not video_id.strip():
        return _error("invalid_video_id", "video_id must not be empty.")

    model_name = model_name or _video_model()
    ok, response = _request_json(
        "GET",
        f"/agnesapi?video_id={quote(video_id, safe='')}&model_name={quote(model_name, safe='')}",
        base_url=_domain_root(),
    )
    if not ok:
        response["video_id"] = video_id
        return response

    return _video_success_result(
        response,
        fallback_video_id=video_id,
        include_raw=include_raw,
    )


def _download_video(
    video_url: str,
    *,
    output_filename: str | None = None,
) -> tuple[bool, str | dict[str, Any]]:
    return _download_url(
        video_url,
        _ensure_output_dir("videos"),
        filename=output_filename,
        default_suffix=".mp4",
        timeout_seconds=600.0,
    )


def _agnes_video_wait_impl(
    video_id: str,
    *,
    model_name: str | None = None,
    timeout_seconds: float = 600.0,
    poll_interval_seconds: float = 5.0,
    download: bool = True,
    output_filename: str | None = None,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        return _error("invalid_timeout", "timeout_seconds must be greater than zero.")
    if poll_interval_seconds <= 0:
        return _error(
            "invalid_poll_interval",
            "poll_interval_seconds must be greater than zero.",
        )

    output_filename = _sanitize_filename(output_filename)

    attempts = max(1, math.ceil(timeout_seconds / poll_interval_seconds) + 1)
    last_response: dict[str, Any] | None = None

    for attempt in range(attempts):
        last_response = _agnes_video_status_impl(
            video_id, model_name=model_name, include_raw=True
        )
        if not last_response.get("ok"):
            error = last_response.get("error")
            details = error.get("details") if isinstance(error, dict) else None
            status_code = details.get("status_code") if isinstance(details, dict) else None
            if status_code in {429, 503} and attempt < attempts - 1:
                time.sleep(poll_interval_seconds)
                continue
            return last_response

        status = str(last_response.get("status") or "").lower()
        if status == "completed":
            video_url = last_response.get("video_url")
            local_path = None
            download_error = None
            if download and isinstance(video_url, str):
                ok, path_or_error = _download_video(
                    video_url,
                    output_filename=output_filename,
                )
                if ok:
                    local_path = path_or_error
                else:
                    download_error = path_or_error["error"]  # type: ignore[index]
            result = dict(last_response)
            result.pop("raw", None)
            result["local_path"] = local_path
            if download_error:
                result["download_error"] = download_error
            return result

        if status == "failed":
            return _error(
                "task_failed",
                "Agnes video task failed.",
                video_id=video_id,
                last_response=last_response,
            )

        if attempt < attempts - 1:
            time.sleep(poll_interval_seconds)

    return _error(
        "timeout",
        "Timed out waiting for Agnes video task to complete.",
        video_id=video_id,
        last_response=last_response,
    )


def _agnes_video_generate_impl(
    prompt: str,
    *,
    model: str | None = None,
    mode: str = "text",
    seconds: str = "5",
    size: str = "720P",
    aspect_ratio: str = "16:9",
    seed: int | None = None,
    first_frame: str | None = None,
    last_frame: str | None = None,
    images: list[str] | None = None,
    audios: list[str] | None = None,
    videos: list[dict[str, Any]] | None = None,
    timeout_seconds: float = 600.0,
    poll_interval_seconds: float = 5.0,
    download: bool = True,
    output_filename: str | None = None,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    submit_result = _agnes_video_submit_impl(
        prompt,
        model=model,
        mode=mode,
        seconds=seconds,
        size=size,
        aspect_ratio=aspect_ratio,
        seed=seed,
        first_frame=first_frame,
        last_frame=last_frame,
        images=images,
        audios=audios,
        videos=videos,
        extra_body=extra_body,
        include_raw=True,
    )
    if not submit_result.get("ok"):
        return submit_result

    video_id = submit_result.get("video_id")
    if not isinstance(video_id, str) or not video_id:
        return _error(
            "missing_video_id",
            "Agnes video submission succeeded but no video id was found.",
            details={"submit_result": submit_result},
        )

    wait_result = _agnes_video_wait_impl(
        video_id,
        model_name=model or _video_model(),
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        download=download,
        output_filename=output_filename,
    )
    if not wait_result.get("ok"):
        wait_result["submit_result"] = submit_result
    return wait_result


@mcp.tool()
def agnes_image_generate(
    prompt: str,
    size: str = "1024x1024",
    ratio: str | None = None,
    return_base64: bool | None = None,
    response_format: str | None = None,
    image_urls: list[str] | None = None,
    output_filename: str | None = None,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate an image with Agnes Image 2.5 Flash (default; 2.1/2.0-flash via env).

    Supports text-to-image, image-to-image and multi-image composition (via
    image_urls). All three image models support tier sizes '1K'-'4K' with
    'ratio' ('1:1','3:4','4:3','16:9','9:16','2:3','3:2','21:9'), plus legacy
    exact sizes like '1024x768'. Put 'response_format' inside extra_body
    (top-level response_format is rejected); pass 'return_base64' top-level
    for base64 text-to-image. Never send tags: ["img2img"].
    """
    return _agnes_image_generate_impl(
        prompt,
        ratio=ratio,
        size=size,
        return_base64=return_base64,
        response_format=response_format,
        image_urls=image_urls,
        output_filename=output_filename,
        extra_body=extra_body,
    )


@mcp.tool()
def agnes_image_generate_v2(
    prompt: str,
    size: str = "1K",
    ratio: str = "1:1",
    return_base64: bool | None = None,
    response_format: str | None = None,
    image_urls: list[str] | None = None,
    output_filename: str | None = None,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate an image with Agnes Image 2.5 Flash (default) tuned for high-information-density visuals.

    Same request schema as agnes_image_generate but with tier-based sizing:
    size '1K'/'2K'/'3K'/'4K' + ratio ('1:1','3:4','4:3','16:9','9:16','2:3',
    '3:2','21:9'). Legacy exact sizes like '1024x768' are accepted and may be
    normalized. image_urls enables image-to-image and multi-image composition.
    """
    return _agnes_image_generate_impl(
        prompt,
        model=_image_model_v2(),
        size=size,
        ratio=ratio,
        return_base64=return_base64,
        response_format=response_format,
        image_urls=image_urls,
        output_filename=output_filename,
        extra_body=extra_body,
    )


@mcp.tool()
def agnes_image_edit(
    prompt: str,
    image_paths: list[str],
    mask_path: str | None = None,
    size: str = "1024x1024",
    ratio: str | None = None,
    return_base64: bool | None = None,
    response_format: str | None = None,
    output_filename: str | None = None,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Edit, restyle, or compose images through Agnes img2img using URLs or local files.

    Defaults to agnes-image-2.5-flash. Pass image_paths as public URLs, Data
    URI base64, or local file paths. Multiple images enable multi-image
    composition. Use tier size ('1K'-'4K') + ratio for predictable dimensions.
    """
    return _agnes_image_edit_impl(
        prompt,
        image_paths,
        mask_path=mask_path,
        size=size,
        ratio=ratio,
        return_base64=return_base64,
        response_format=response_format,
        output_filename=output_filename,
        extra_body=extra_body,
    )


@mcp.tool()
def agnes_video_submit(
    prompt: str,
    mode: str = "text",
    seconds: str = "5",
    size: str = "720P",
    aspect_ratio: str = "16:9",
    seed: int | None = None,
    first_frame: str | None = None,
    last_frame: str | None = None,
    images: list[str] | None = None,
    audios: list[str] | None = None,
    videos: list[dict[str, Any]] | None = None,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Submit an Agnes video task (async) and return video_id + task_id.

    Default model is agnes-video-2.5-flash (free, limited-time; 720P only,
    images<=5, audios<=3, no reference videos). Set AGNES_VIDEO_MODEL or pass
    model via extra_body to use agnes-video-2.5 (paid: 720P $0.025/s,
    1080P/1K $0.040/s, 2K $0.055/s) or agnes-video-v2.0.

    mode='text': prompt only. mode='keyframe': first_frame and/or last_frame
    URLs. mode='reference': images and/or audios (2.5 also videos), referenced
    in the prompt as <Picture 1>/<Audio 1>/<Video 1>.
    seconds is a string '4'-'12'; size 720P/1080P/1K/2K (flash: 720P only).
    """
    return _agnes_video_submit_impl(
        prompt,
        mode=mode,
        seconds=seconds,
        size=size,
        aspect_ratio=aspect_ratio,
        seed=seed,
        first_frame=first_frame,
        last_frame=last_frame,
        images=images,
        audios=audios,
        videos=videos,
        extra_body=extra_body,
    )


@mcp.tool()
def agnes_video_status(
    video_id: str,
    model_name: str | None = None,
) -> dict[str, Any]:
    """Fetch the current status of an Agnes video task.

    Recommended query form: video_id + model_name (defaults to the configured
    video model). A bare video_id query only works for mode='text' tasks.
    """
    return _agnes_video_status_impl(video_id, model_name=model_name)


@mcp.tool()
async def agnes_video_wait(
    video_id: str,
    model_name: str | None = None,
    timeout_seconds: float = 600.0,
    poll_interval_seconds: float = 5.0,
    download: bool = True,
    output_filename: str | None = None,
) -> dict[str, Any]:
    """Poll a video task by video_id until it completes, fails, or times out.

    Poll every 1-2s server-side in production; this tool sleeps
    poll_interval_seconds between checks. When status='completed' the video
    is downloaded to the local output directory.
    """
    return await asyncio.to_thread(
        _agnes_video_wait_impl,
        video_id,
        model_name=model_name,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        download=download,
        output_filename=output_filename,
    )


@mcp.tool()
async def agnes_video_generate(
    prompt: str,
    mode: str = "text",
    seconds: str = "5",
    size: str = "720P",
    aspect_ratio: str = "16:9",
    seed: int | None = None,
    first_frame: str | None = None,
    last_frame: str | None = None,
    images: list[str] | None = None,
    audios: list[str] | None = None,
    videos: list[dict[str, Any]] | None = None,
    timeout_seconds: float = 600.0,
    poll_interval_seconds: float = 5.0,
    download: bool = True,
    output_filename: str | None = None,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Submit an Agnes video task and wait for completion.

    Combines submit + wait. Returns the final video_url and downloads the
    video file locally. Uses agnes-video-2.5-flash by default (free);
    see agnes_video_submit for mode/media rules and paid-model notes.
    """
    return await asyncio.to_thread(
        _agnes_video_generate_impl,
        prompt,
        model=None,
        mode=mode,
        seconds=seconds,
        size=size,
        aspect_ratio=aspect_ratio,
        seed=seed,
        first_frame=first_frame,
        last_frame=last_frame,
        images=images,
        audios=audios,
        videos=videos,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        download=download,
        output_filename=output_filename,
        extra_body=extra_body,
    )


def main() -> None:
    """Console-script entry point for ``uvx agnes-media-mcp``."""
    mcp.run()


if __name__ == "__main__":
    main()
