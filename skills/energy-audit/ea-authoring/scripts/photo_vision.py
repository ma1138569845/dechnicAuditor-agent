"""DeepSeek 视觉模型对第3章证书照片做第二层核验。

数据库/文件名负责确定候选照片；本模块只读取候选图片并核对证书标题、
受奖单位等内容。模型不可用时返回 unverified，由调用方提示但不阻断。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional


DEFAULT_MODEL = "deepseek-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
PROMPT_VERSION = "certificate-check-v2"
GENERAL_PROMPT_VERSION = "photo-fact-v1"
MIN_CONFIDENCE = 0.80
MAX_IMAGE_BYTES = 32 * 1024 * 1024

_TITLE_SUFFIXES = (
    "荣誉证书",
    "获奖证书",
    "证书",
    "奖牌",
    "牌匾",
    "奖杯",
    "文件",
    "截图",
)
_SMALL_WORD_RE = re.compile(r"[\s/／\\、，,。.；;：:（）()\[\]【】\-—_]+")
_YEAR_RE = re.compile(r"(?:19|20)\d{2}年?")


def normalize_claim_text(value: Any, *, strip_document_suffix: bool = True) -> str:
    text = _SMALL_WORD_RE.sub("", str(value or "")).lower()
    if strip_document_suffix:
        text = _YEAR_RE.sub("", text)
        changed = True
        while changed:
            changed = False
            for suffix in _TITLE_SUFFIXES:
                if text.endswith(suffix) and len(text) > len(suffix):
                    text = text[:-len(suffix)]
                    changed = True
    return text


def _truthy(value: Any) -> bool:
    if value is True:
        return True
    return str(value).strip().lower() in {"1", "true", "yes", "是"}


def evaluate_verification(
    *,
    expected_title: str,
    expected_recipient: str,
    observed: Dict[str, Any],
) -> Dict[str, Any]:
    """把模型读数与报告声明做确定性比较。"""
    observed = observed or {}
    confidence = observed.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = None

    if not _truthy(observed.get("is_single_certificate", True)):
        return {"status": "review", "reason": "图片中不是单一证书，需人工指定具体证书"}
    if confidence is None or confidence < MIN_CONFIDENCE:
        return {
            "status": "review",
            "reason": f"视觉识别置信度不足（{confidence if confidence is not None else '未知'}）",
        }

    visible_title = observed.get("visible_title") or ""
    title_expected = normalize_claim_text(expected_title)
    title_observed = normalize_claim_text(visible_title)
    if not title_observed:
        return {"status": "review", "reason": "图片中未识别到可核对的证书标题"}
    if title_expected not in title_observed and title_observed not in title_expected:
        return {
            "status": "mismatch",
            "reason": f"证书标题不一致：图注/数据库为“{expected_title}”，图片识别为“{visible_title}”",
        }

    recipient_expected = normalize_claim_text(expected_recipient, strip_document_suffix=False)
    recipient_observed = normalize_claim_text(
        observed.get("recipient") or "", strip_document_suffix=False
    )
    if recipient_expected and recipient_observed and \
            recipient_expected not in recipient_observed and \
            recipient_observed not in recipient_expected:
        return {
            "status": "mismatch",
            "reason": (
                f"受奖单位不一致：报告单位为“{expected_recipient}”，"
                f"图片识别为“{observed.get('recipient')}”"
            ),
        }

    return {"status": "pass", "reason": "证书标题和受奖单位与数据一致"}


def _image_data_url(image_path: str) -> str:
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(image_path)
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError(f"图片超过视觉接口 32 MiB 限制: {path}")
    raw = path.read_bytes()
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        media_type = "image/png"
    elif raw.startswith(b"\xff\xd8\xff"):
        media_type = "image/jpeg"
    elif raw.startswith((b"GIF87a", b"GIF89a")):
        media_type = "image/gif"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        media_type = "image/webp"
    else:
        raise ValueError(f"视觉接口不支持该图片格式: {path}")
    return f"data:{media_type};base64,{base64.b64encode(raw).decode('ascii')}"


def _post_json(url: str, headers: Dict[str, str], payload: Dict, timeout: int) -> Dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _message_text(response: Dict[str, Any]) -> str:
    message = (response.get("choices") or [{}])[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        if content.strip():
            return content
    if isinstance(content, list):
        text = "\n".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
        )
        if text.strip():
            return text
    # 兼容少数响应把内容放入 reasoning_content 的情况。正常调用已显式关闭
    # thinking；此分支只用于避免网关或模型升级造成“有结果但 content 为空”。
    return str(message.get("reasoning_content") or content or "")


def parse_vision_response(response: Dict[str, Any]) -> Dict[str, Any]:
    text = _message_text(response).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("视觉模型未返回 JSON 对象")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("视觉模型返回的 JSON 不是对象")
    return data


def _vision_prompt(expected_title: str, expected_recipient: str) -> str:
    return f"""你是能源审计报告的证书核验员。请只读取图片中肉眼可见的内容，不推断、不补全。
报告声称：证书标题为“{expected_title}”，受奖单位为“{expected_recipient}”。
请判断图片是否为单一证书/奖牌/制度文件，并返回一个 JSON 对象，字段固定为：
{{
  "document_type": "荣誉证书|奖牌|制度文件|其他",
  "visible_title": "图片中最醒目的正式标题；看不清填空字符串",
  "recipient": "证书上的受奖单位；没有或看不清填空字符串",
  "issuer": "颁发单位；没有或看不清填空字符串",
  "date": "证书日期；没有或看不清填空字符串",
  "is_single_certificate": true,
  "confidence": 0.0
}}
confidence 取 0 到 1。图片模糊、包含多张证书或无法确认时必须降低 confidence。"""


def _resolve_api_key(env: Optional[Dict[str, str]] = None) -> str:
    values = os.environ if env is None else env
    key = str(values.get("DEEPSEEK_API_KEY") or "").strip()
    if key:
        return key

    candidates = []
    hermes_home = str(values.get("HERMES_HOME") or "").strip()
    if hermes_home:
        candidates.append(Path(hermes_home) / ".env")
    local_appdata = str(values.get("LOCALAPPDATA") or "").strip()
    if local_appdata:
        candidates.append(Path(local_appdata) / "hermes" / ".env")
    candidates.append(Path.home() / "AppData" / "Local" / "hermes" / ".env")

    for path in candidates:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == "DEEPSEEK_API_KEY":
                return value.strip().strip('"').strip("'")
    return ""


def verify_certificate(
    *,
    image_path: str,
    expected_title: str,
    expected_recipient: str,
    api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = 45,
    poster: Optional[Callable[[str, Dict, Dict, int], Dict]] = None,
) -> Dict[str, Any]:
    """核验单张候选证书；任何接口异常都降级为 unverified。"""
    key = api_key if api_key is not None else _resolve_api_key()
    if not key:
        return {
            "status": "unverified",
            "reason": "未配置 DEEPSEEK_API_KEY，跳过视觉核验",
            "model": model,
        }

    try:
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": _vision_prompt(expected_title, expected_recipient)},
                    {
                        "type": "image_url",
                        "image_url": {"url": _image_data_url(image_path), "detail": "high"},
                    },
                ],
            }],
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 800,
        }
        request = poster or _post_json
        response = request(
            f"{base_url.rstrip('/')}/chat/completions",
            {"Authorization": f"Bearer {key}"},
            payload,
            timeout,
        )
        observed = parse_vision_response(response)
        verdict = evaluate_verification(
            expected_title=expected_title,
            expected_recipient=expected_recipient,
            observed=observed,
        )
        return {
            **verdict,
            "observed": observed,
            "model": model,
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unverified",
            "reason": f"视觉核验不可用：{exc}",
            "model": model,
        }


def _photo_fact_prompt(expected_context: str) -> str:
    return f"""你是能源审计报告的照片事实提取员。数据库把这张照片绑定为“{expected_context}”。
请只读取图片中肉眼可见的内容，不推断、不补全，也不要把数据库绑定当成图片事实。
返回一个 JSON 对象，字段固定为：
{{
  "scene_type": "建筑外观|设备|仪表|证书|文件|其他",
  "visible_title": "图片中最醒目的正式文字标题；看不清填空字符串",
  "object_labels": ["可直接看到的物体或设备名称"],
  "brand": "清晰可见的品牌；看不清填空字符串",
  "model": "清晰可见的型号；看不清填空字符串",
  "confidence": 0.0
}}
confidence 取 0 到 1。图片模糊、主体不明确或文字无法确认时必须降低 confidence。"""


def _visible_photo_facts(observed: Dict[str, Any]) -> Dict[str, Any]:
    labels = observed.get("object_labels")
    if not isinstance(labels, list):
        labels = []
    facts = {
        "scene_type": str(observed.get("scene_type") or "").strip(),
        "visible_title": str(observed.get("visible_title") or "").strip(),
        "object_labels": [
            str(label).strip()
            for label in labels
            if str(label).strip()
        ],
        "brand": str(observed.get("brand") or "").strip(),
        "model": str(observed.get("model") or "").strip(),
    }
    try:
        confidence = float(observed.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    facts["confidence"] = confidence
    return facts


def inspect_photo(
    *,
    image_path: str,
    expected_context: str,
    api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = 45,
    poster: Optional[Callable[[str, Dict, Dict, int], Dict]] = None,
) -> Dict[str, Any]:
    """Extract visible photo facts; failures remain non-blocking."""
    key = api_key if api_key is not None else _resolve_api_key()
    if not key:
        return {
            "status": "unverified",
            "reason": "未配置 DEEPSEEK_API_KEY，跳过照片事实提取",
            "observed": {},
            "model": model,
        }

    try:
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": _photo_fact_prompt(expected_context),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": _image_data_url(image_path),
                            "detail": "high",
                        },
                    },
                ],
            }],
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 800,
        }
        request = poster or _post_json
        response = request(
            f"{base_url.rstrip('/')}/chat/completions",
            {"Authorization": f"Bearer {key}"},
            payload,
            timeout,
        )
        observed = _visible_photo_facts(parse_vision_response(response))
        confidence = observed["confidence"]
        status = "pass" if confidence >= MIN_CONFIDENCE else "review"
        reason = (
            ""
            if status == "pass"
            else f"视觉识别置信度不足（{confidence}）"
        )
        return {
            "status": status,
            "reason": reason,
            "observed": observed,
            "model": model,
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unverified",
            "reason": f"照片事实提取不可用：{exc}",
            "observed": {},
            "model": model,
        }


def vision_cache_key(
    *,
    image_path: str,
    expected_title: str,
    expected_recipient: str,
    model: str = DEFAULT_MODEL,
) -> str:
    digest = hashlib.sha256(Path(image_path).read_bytes()).hexdigest()
    payload = "|".join((
        digest,
        normalize_claim_text(expected_title),
        normalize_claim_text(expected_recipient, strip_document_suffix=False),
        str(model or ""),
        PROMPT_VERSION,
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
