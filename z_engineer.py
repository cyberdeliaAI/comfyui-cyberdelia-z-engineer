import time

import requests

from .model_utils import chat_completions_endpoint, resolve_model_name
from .prompt_utils import (
    build_preservation_instruction,
    enforce_constraints,
    enforce_keep_terms,
    extract_constraints,
    parse_keep_terms,
    sanitize_output,
)
from .vision_utils import build_vision_user_content, image_to_data_url


class CyberdeliaZEngineer:
    """
    Legacy-compatible conditioning variant of Cyberdelia Prompt Engineer.
    Sends an input prompt to an OpenAI-compatible LLM endpoint, receives an
    engineered prompt back, and CLIP-encodes it directly to a positive
    conditioning output. Also returns an empty negative conditioning for
    save-node compatibility.

    The user-facing text widget is named `text` so that downstream metadata
    extension/save nodes that follow the standard CLIPTextEncode pattern can
    capture the prompt automatically (they fall back to scanning for `text`,
    `string`, or `prompt` fields on intermediate conditioning nodes).
    """

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "clip": ("CLIP",),
                "mode": ("BOOLEAN", {
                    "default": True,
                    "label_on": "✨ engineered (LLM)",
                    "label_off": "→ passthrough (raw)"
                }),
                "text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Enter your prompt here..."
                }),
                "system_prompt": ("STRING", {
                    "multiline": True,
                    "default": "You are a helpful assistant.",
                    "placeholder": "Enter system prompt here..."
                }),
                "api_url": ("STRING", {
                    "multiline": False,
                    "default": "http://localhost:1234/v1",
                }),
                "model": ("STRING", {
                    "multiline": False,
                    "default": "auto",
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xffffffffffffffff
                }),
                "temperature": ("FLOAT", {
                    "default": 0.7,
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.01
                }),
                "max_tokens": ("INT", {
                    "default": 600,
                    "min": 50,
                    "max": 4096,
                    "step": 1
                }),
                "timeout": ("INT", {
                    "default": 120,
                    "min": 10,
                    "max": 600,
                    "step": 1
                }),
            },
            "optional": {
                "keep_terms": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "placeholder": "Exact terms, separated by commas...",
                }),
                "preserve_constraints": ("BOOLEAN", {
                    "default": False,
                    "label_on": "preserve seed constraints",
                    "label_off": "model decides",
                }),
                "clean_output": ("BOOLEAN", {
                    "default": True,
                    "label_on": "clean LLM output",
                    "label_off": "raw LLM output",
                }),
                "error_mode": (["fallback_input", "stop", "empty"], {
                    "default": "fallback_input",
                }),
                "retries": ("INT", {
                    "default": 1,
                    "min": 0,
                    "max": 3,
                    "step": 1,
                }),
                "use_vision": ("BOOLEAN", {
                    "default": False,
                    "label_on": "vision image → prompt",
                    "label_off": "normal text → prompt",
                }),
                "vision_system_prompt": ("STRING", {
                    "multiline": True,
                    "default": (
                        "Analyze the attached image and return only one detailed "
                        "image-generation prompt in English."
                    ),
                    "placeholder": "Instructions used only when Vision is enabled...",
                }),
                "image": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("CONDITIONING", "CONDITIONING", "STRING")
    RETURN_NAMES = ("positive", "negative", "prompt")
    FUNCTION = "generate_prompt"
    CATEGORY = "Cyberdelia/Prompt"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _encode(self, clip, text):
        """Tokenize and CLIP-encode a text string into CONDITIONING."""
        tokens = clip.tokenize(text)
        return clip.encode_from_tokens_scheduled(tokens)

    def _record_resolved_text(self, text):
        """Push the actually-encoded positive text to any metadata extension
        that's listening, keyed by node_id + output slot 0 (positive).

        We DO NOT push for the negative output (slot 1) — it's an encoded
        empty string, and the slot-aware walker treats the absence of a
        registered slot as a definitive "no text here" (so metadata reports
        empty negative correctly, instead of falling back to the input
        widget which still contains the raw user text).

        Loose-coupled via sys.modules scan — no hard dependency on any
        specific metadata extension.

        Implementation note: we use mod.__dict__.get() rather than
        getattr() to avoid triggering lazy __getattr__ descriptors in
        third-party libraries (e.g. transformers' deprecation system,
        which emits a warning for every submodule on getattr() with an
        unknown name).
        """
        if not text:
            return
        try:
            import sys
            from comfy_execution.utils import get_executing_context
            context = get_executing_context()
            if context is None:
                return
            node_id = str(context.node_id)
            slot_key = f"{node_id}:0"  # slot 0 = positive output
            for mod in list(sys.modules.values()):
                if mod is None:
                    continue
                mod_dict = getattr(mod, "__dict__", None)
                if mod_dict is None:
                    continue
                cache = mod_dict.get("current_resolved_texts")
                if isinstance(cache, dict):
                    try:
                        cache[slot_key] = text
                    except Exception:
                        pass
        except Exception:
            pass  # Either ComfyUI is too old, or no metadata extension is loaded

    @staticmethod
    def _is_retryable_error(exc):
        if isinstance(exc, (requests.exceptions.ConnectionError,
                            requests.exceptions.Timeout)):
            return True
        if isinstance(exc, requests.exceptions.HTTPError):
            response = exc.response
            status = response.status_code if response is not None else None
            return status == 429 or (status is not None and status >= 500)
        return False

    @staticmethod
    def _retry_delay(exc, attempt):
        if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
            retry_after = exc.response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(max(float(retry_after), 0.0), 10.0)
                except ValueError:
                    pass
        return min(2 ** attempt, 4)

    @staticmethod
    def _extract_message_content(data):
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM response did not contain a chat message") from exc

        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") in {None, "text"}
            )
        content = str(content or "").strip()
        if content:
            return content

        reasoning = message.get("reasoning_content") or message.get("reasoning")
        if reasoning:
            raise RuntimeError(
                "LLM returned reasoning but no final content; increase max_tokens "
                "or adjust the model's reasoning settings"
            )
        raise RuntimeError("LLM returned an empty response")

    def _call_llm(self, text, system_prompt, api_url, model,
                  seed, temperature, max_tokens, timeout, retries=1,
                  image_data_url=None):
        """Send a chat completion request to the OpenAI-compatible endpoint."""
        endpoint = chat_completions_endpoint(api_url)
        headers = {"Content-Type": "application/json"}
        user_content = (
            build_vision_user_content(text, image_data_url)
            if image_data_url
            else text
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": temperature,
            "seed": seed,
            "max_tokens": max_tokens,
            "stream": False,
        }

        attempts = max(1, int(retries) + 1)
        for attempt in range(attempts):
            try:
                print(
                    f"[Prompt Engineer] POST {endpoint} (model: {model}, "
                    f"attempt: {attempt + 1}/{attempts})"
                )
                response = requests.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                )
                response.raise_for_status()
                return self._extract_message_content(response.json())
            except Exception as exc:
                if attempt + 1 >= attempts or not self._is_retryable_error(exc):
                    raise
                delay = self._retry_delay(exc, attempt)
                print(
                    f"[Prompt Engineer] Temporary LLM error: {exc}. "
                    f"Retrying in {delay:g}s."
                )
                time.sleep(delay)

        raise RuntimeError("LLM request failed without an error")

    @staticmethod
    def _log_failure(exc, api_url, model, timeout):
        if isinstance(exc, requests.exceptions.ConnectionError):
            print(f"[Prompt Engineer] ⚠️  Could not reach LLM at {api_url}")
            print("[Prompt Engineer]    Server not running, wrong URL, or blocked by firewall.")
        elif isinstance(exc, requests.exceptions.Timeout):
            print(f"[Prompt Engineer] ⚠️  LLM request timed out after {timeout}s at {api_url}")
        elif isinstance(exc, requests.exceptions.HTTPError):
            status = exc.response.status_code if exc.response is not None else "?"
            print(f"[Prompt Engineer] ⚠️  LLM returned HTTP {status} at {api_url}")
            print(f"[Prompt Engineer]    Check model '{model}' and the server request settings.")
        else:
            print(f"[Prompt Engineer] ⚠️  LLM call failed: {exc}")

    # ------------------------------------------------------------------
    # Main
    # ------------------------------------------------------------------

    def _generate_final_text(self, mode, text, system_prompt,
                             api_url, model, seed, temperature, max_tokens, timeout,
                             keep_terms="", preserve_constraints=False,
                             clean_output=True, error_mode="fallback_input", retries=1,
                             use_vision=False, vision_system_prompt="", image=None):
        """Run the shared text/vision prompt pipeline without encoding it."""

        input_text = str(text or "")
        vision_requested = bool(use_vision)
        has_image = vision_requested and image is not None

        # Step 1: decide what text we ultimately want to encode
        if not mode:
            # Passthrough — use raw user input
            final_text = input_text
            print("[Prompt Engineer] Passthrough mode — using input text unchanged")

        elif not input_text.strip() and not vision_requested:
            # Engineered mode but no input — skip LLM call
            final_text = ""
            print("[Prompt Engineer] Empty input text — returning empty prompt")

        else:
            # Engineered mode — call the LLM
            resolved_model = str(model or "").strip() or "auto"
            try:
                if vision_requested and image is None:
                    raise ValueError(
                        "Vision mode is enabled but no image is connected"
                    )
                resolved_model = resolve_model_name(
                    model,
                    api_url,
                    timeout=timeout,
                    require_vision=vision_requested,
                )
                parsed_keep_terms = parse_keep_terms(keep_terms)
                constraints = (
                    extract_constraints(input_text) if preserve_constraints else []
                )
                preservation_instruction = build_preservation_instruction(
                    parsed_keep_terms,
                    constraints,
                )
                selected_system_prompt = (
                    vision_system_prompt if vision_requested else system_prompt
                )
                resolved_system_prompt = str(selected_system_prompt or "").strip()
                if preservation_instruction:
                    resolved_system_prompt = (
                        f"{resolved_system_prompt}\n\n{preservation_instruction}"
                        if resolved_system_prompt
                        else preservation_instruction
                    )

                image_data_url = image_to_data_url(image) if has_image else None
                raw_text = self._call_llm(
                    input_text, resolved_system_prompt, api_url, resolved_model,
                    seed, temperature, max_tokens, timeout, retries,
                    image_data_url,
                )
                final_text = sanitize_output(raw_text) if clean_output else raw_text.strip()
                if not final_text:
                    raise RuntimeError("LLM output was empty after cleaning")
                if preserve_constraints:
                    final_text = enforce_constraints(final_text, constraints)
                if parsed_keep_terms:
                    final_text = enforce_keep_terms(final_text, parsed_keep_terms)

                preview = final_text[:100].replace("\n", " ")
                print(
                    f"[Prompt Engineer] Engineered with '{resolved_model}' "
                    f"{'(vision) ' if has_image else ''}"
                    f"({len(final_text)} chars): {preview}..."
                )
            except Exception as exc:
                self._log_failure(exc, api_url, resolved_model, timeout)
                normalized_error_mode = str(error_mode or "fallback_input").casefold()
                if normalized_error_mode == "stop":
                    raise
                if normalized_error_mode == "empty":
                    print("[Prompt Engineer]    Returning empty prompt.")
                    final_text = ""
                else:
                    print("[Prompt Engineer]    Falling back to input text (passthrough).")
                    final_text = input_text

        return final_text

    def generate_prompt(self, clip, mode, text, system_prompt,
                        api_url, model, seed, temperature, max_tokens, timeout,
                        keep_terms="", preserve_constraints=False,
                        clean_output=True, error_mode="fallback_input", retries=1,
                        use_vision=False, vision_system_prompt="", image=None):

        final_text = self._generate_final_text(
            mode, text, system_prompt, api_url, model, seed, temperature,
            max_tokens, timeout, keep_terms, preserve_constraints, clean_output,
            error_mode, retries, use_vision, vision_system_prompt, image,
        )

        # Step 2: push final_text to any listening metadata extension
        # so the engineered output ends up in saved image metadata
        # instead of the raw widget value.
        self._record_resolved_text(final_text)

        # Step 3: CLIP-encode positive
        positive = self._encode(clip, final_text)

        # Step 4: CLIP-encode empty string for negative (save-node compatible)
        negative = self._encode(clip, "")

        return (positive, negative, final_text)
