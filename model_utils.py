"""OpenAI-compatible URL handling and LM Studio model discovery."""

import threading
import time
from urllib.parse import urlsplit, urlunsplit

import requests


MODEL_CACHE_TTL_SECONDS = 20.0
_MODEL_CACHE = {}
_MODEL_CACHE_LOCK = threading.Lock()


class ModelDiscoveryError(RuntimeError):
    """Raised when automatic model selection cannot make a safe choice."""


def normalize_openai_base_url(api_url):
    """Normalize a server URL to an OpenAI-compatible ``.../v1`` base."""
    value = str(api_url or "").strip().rstrip("/")
    if not value:
        raise ValueError("API URL is empty")

    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("API URL must be an http:// or https:// URL")

    path = parsed.path.rstrip("/")
    suffix = "/chat/completions"
    if path.endswith(suffix):
        path = path[:-len(suffix)].rstrip("/")
    if not path.endswith("/v1"):
        path = f"{path}/v1" if path else "/v1"

    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def chat_completions_endpoint(api_url):
    return f"{normalize_openai_base_url(api_url)}/chat/completions"


def lmstudio_server_root(api_url):
    """Return the server root used by LM Studio's native ``/api/v1`` API."""
    base = normalize_openai_base_url(api_url)
    parsed = urlsplit(base)
    path = parsed.path
    if path.endswith("/v1"):
        path = path[:-3].rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _native_models(api_url, timeout):
    endpoint = f"{lmstudio_server_root(api_url)}/api/v1/models"
    response = requests.get(endpoint, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    models = []
    for item in data.get("models", []):
        model_type = str(item.get("type", "")).casefold()
        if model_type in {"embedding", "embeddings"}:
            continue
        model_id = str(item.get("key", "")).strip()
        if not model_id:
            continue
        capabilities = item.get("capabilities") or {}
        vision_capability = (
            capabilities.get("vision") if isinstance(capabilities, dict) else False
        )
        supports_vision = (
            vision_capability is True
            or str(vision_capability).casefold() == "true"
            or model_type in {"vision", "vlm"}
        )
        instances = [
            str(instance.get("id", "")).strip()
            for instance in (item.get("loaded_instances") or [])
            if instance.get("id")
        ]
        models.append(
            {
                "id": model_id,
                "loaded": bool(instances),
                "instances": instances,
                "source": "lmstudio",
                "vision": supports_vision,
            }
        )
    return models


def _openai_models(api_url, timeout):
    endpoint = f"{normalize_openai_base_url(api_url)}/models"
    response = requests.get(endpoint, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    models = []
    for item in data.get("data", []):
        model_type = str(item.get("type", "")).casefold()
        if model_type in {"embedding", "embeddings"}:
            continue
        model_id = str(item.get("id", "")).strip()
        if model_id:
            capabilities = item.get("capabilities") or {}
            if isinstance(capabilities, dict):
                vision_capability = capabilities.get("vision")
                supports_vision = (
                    vision_capability is True
                    or str(vision_capability).casefold() == "true"
                )
            elif isinstance(capabilities, (list, tuple, set)):
                supports_vision = any(
                    str(capability).casefold() in {"vision", "image", "image_input"}
                    for capability in capabilities
                )
            else:
                supports_vision = False
            models.append(
                {
                    "id": model_id,
                    "loaded": False,
                    "instances": [],
                    "source": "openai",
                    "vision": supports_vision,
                }
            )
    return models


def _deduplicate_models(models):
    by_id = {}
    for model in models:
        current = by_id.get(model["id"])
        if current is None or (model.get("loaded") and not current.get("loaded")):
            by_id[model["id"]] = model
    return sorted(
        by_id.values(),
        key=lambda item: (not item.get("loaded", False), item["id"].casefold()),
    )


def clear_model_cache(api_url=None):
    with _MODEL_CACHE_LOCK:
        if api_url is None:
            _MODEL_CACHE.clear()
            return
        try:
            key = normalize_openai_base_url(api_url)
        except ValueError:
            return
        _MODEL_CACHE.pop(key, None)


def discover_models(api_url, timeout=2.0, force=False):
    """Discover LLMs, preferring LM Studio's richer native model endpoint."""
    cache_key = normalize_openai_base_url(api_url)
    now = time.monotonic()
    if not force:
        with _MODEL_CACHE_LOCK:
            cached = _MODEL_CACHE.get(cache_key)
            if cached and now - cached[0] < MODEL_CACHE_TTL_SECONDS:
                return [dict(model) for model in cached[1]]

    errors = []
    models = []
    try:
        models = _native_models(api_url, timeout)
    except Exception as exc:
        errors.append(f"LM Studio endpoint: {exc}")

    if not models:
        try:
            models = _openai_models(api_url, timeout)
        except Exception as exc:
            errors.append(f"OpenAI endpoint: {exc}")

    models = _deduplicate_models(models)
    if not models:
        detail = "; ".join(errors) or "the server returned no LLMs"
        raise ModelDiscoveryError(f"Could not discover an LLM at {cache_key}: {detail}")

    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE[cache_key] = (now, [dict(model) for model in models])
    return models


def resolve_model_name(requested_model, api_url, timeout=2.0, require_vision=False):
    """Resolve ``auto`` only when discovery produces one unambiguous choice."""
    requested = str(requested_model or "").strip()
    if requested and requested.casefold() != "auto":
        return requested

    discovery_timeout = min(max(float(timeout), 0.5), 5.0)
    models = discover_models(api_url, timeout=discovery_timeout)
    if require_vision:
        models = [model for model in models if model.get("vision") is True]
        if not models:
            raise ModelDiscoveryError(
                "Auto model selection found no vision-capable model; "
                "choose a vision model manually"
            )
    loaded = [model for model in models if model.get("loaded")]
    if len(loaded) == 1:
        return loaded[0]["id"]
    if len(loaded) > 1:
        names = ", ".join(model["id"] for model in loaded)
        model_kind = "vision models" if require_vision else "LLMs"
        raise ModelDiscoveryError(
            f"Auto model selection is ambiguous; multiple {model_kind} are loaded: {names}"
        )
    if len(models) == 1:
        return models[0]["id"]
    names = ", ".join(model["id"] for model in models)
    raise ModelDiscoveryError(
        f"Auto model selection is ambiguous; choose one of these LLMs: {names}"
    )
