import requests


class CyberdeliaZEngineer:
    """
    LLM-powered prompt engineering node for Z-Image Turbo workflows.
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
                    "default": "local-model",
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
        """Push the actually-encoded text to any metadata extension that's
        listening, so save nodes can capture the engineered LLM output
        instead of the raw widget value. Uses loose coupling via sys.modules
        scan — no hard dependency on any specific metadata extension.
        """
        if not text:
            return
        try:
            import sys
            from comfy_execution.utils import get_executing_context
            context = get_executing_context()
            if context is None:
                return
            node_id = context.node_id
            list_index = getattr(context, "list_index", None)
            for mod in list(sys.modules.values()):
                if mod is None:
                    continue
                record_fn = getattr(mod, "record_resolved_text", None)
                cache = getattr(mod, "current_resolved_texts", None)
                if callable(record_fn) and cache is not None:
                    try:
                        record_fn(node_id, text, list_index)
                    except Exception:
                        pass
        except Exception:
            pass  # Either ComfyUI is too old, or no metadata extension is loaded

    def _call_llm(self, text, system_prompt, api_url, model,
                  seed, temperature, max_tokens, timeout):
        """Send a chat completion request to the OpenAI-compatible endpoint."""
        endpoint = f"{api_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            "temperature": temperature,
            "seed": seed,
            "max_tokens": max_tokens,
            "stream": False,
        }

        print(f"[Z-Engineer] POST {endpoint} (model: {model})")
        response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return data['choices'][0]['message']['content'].strip()

    # ------------------------------------------------------------------
    # Main
    # ------------------------------------------------------------------

    def generate_prompt(self, clip, mode, text, system_prompt,
                        api_url, model, seed, temperature, max_tokens, timeout):

        # Step 1: decide what text we ultimately want to encode
        if not mode:
            # Passthrough — use raw user input
            final_text = text
            print("[Z-Engineer] Passthrough mode — using input text unchanged")

        elif not text.strip():
            # Engineered mode but no input — skip LLM call
            final_text = ""
            print("[Z-Engineer] Empty input text — returning empty conditioning")

        else:
            # Engineered mode — call the LLM
            try:
                final_text = self._call_llm(
                    text, system_prompt, api_url, model,
                    seed, temperature, max_tokens, timeout,
                )
                preview = final_text[:100].replace("\n", " ")
                print(f"[Z-Engineer] Engineered ({len(final_text)} chars): {preview}...")
            except Exception as e:
                # Fallback: workflow keeps rendering with the raw input
                print(f"[Z-Engineer] LLM call failed: {e} — falling back to input text")
                final_text = text

        # Step 2: push final_text to any listening metadata extension
        # so the engineered output ends up in saved image metadata
        # instead of the raw widget value.
        self._record_resolved_text(final_text)

        # Step 3: CLIP-encode positive
        positive = self._encode(clip, final_text)

        # Step 4: CLIP-encode empty string for negative (save-node compatible)
        negative = self._encode(clip, "")

        return (positive, negative, final_text)
