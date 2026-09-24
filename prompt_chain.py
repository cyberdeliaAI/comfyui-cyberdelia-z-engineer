"""Sequential multi-prompt processing for Cyberdelia Prompt Engineer."""

from .model_utils import resolve_model_name
from .z_engineer import CyberdeliaZEngineer


CHAIN_STAGE_COUNT = 5
PREVIOUS_OUTPUT_ONLY = "previous output only"
ORIGINAL_AND_PREVIOUS = "original + previous output"


class CyberdeliaPromptEngineerChain(CyberdeliaZEngineer):
    """Run one prompt through a configurable sequence of system prompts."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": ("BOOLEAN", {
                    "default": True,
                    "label_on": "✨ run prompt chain",
                    "label_off": "→ passthrough (raw)",
                }),
                "text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Enter or connect the original prompt...",
                }),
                "stage_count": ("INT", {
                    "default": 3,
                    "min": 1,
                    "max": CHAIN_STAGE_COUNT,
                    "step": 1,
                }),
                "handoff_mode": ([PREVIOUS_OUTPUT_ONLY, ORIGINAL_AND_PREVIOUS], {
                    "default": PREVIOUS_OUTPUT_ONLY,
                }),
                "system_prompt_1": ("STRING", {
                    "multiline": True,
                    "default": (
                        "Rewrite the input into a clear, well-structured image prompt. "
                        "Return only the revised prompt."
                    ),
                    "placeholder": "System prompt for stage 1...",
                }),
                "system_prompt_2": ("STRING", {
                    "multiline": True,
                    "default": (
                        "Improve visual detail, composition, lighting, and atmosphere "
                        "without changing the core concept. Return only the revised prompt."
                    ),
                    "placeholder": "System prompt for stage 2...",
                }),
                "system_prompt_3": ("STRING", {
                    "multiline": True,
                    "default": (
                        "Polish the prompt for clarity and remove repetition. Return only "
                        "the final prompt."
                    ),
                    "placeholder": "System prompt for stage 3...",
                }),
                "system_prompt_4": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Optional system prompt for stage 4...",
                }),
                "system_prompt_5": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Optional system prompt for stage 5...",
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
                    "max": 0xffffffffffffffff,
                }),
                "temperature": ("FLOAT", {
                    "default": 0.7,
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.01,
                }),
                "max_tokens": ("INT", {
                    "default": 600,
                    "min": 50,
                    "max": 4096,
                    "step": 1,
                }),
                "timeout": ("INT", {
                    "default": 120,
                    "min": 10,
                    "max": 600,
                    "step": 1,
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
                    "label_on": "clean every stage",
                    "label_off": "raw LLM output",
                }),
                "error_mode": (["stop", "fallback_input", "empty"], {
                    "default": "stop",
                }),
                "retries": ("INT", {
                    "default": 1,
                    "min": 0,
                    "max": 3,
                    "step": 1,
                }),
            },
        }

    RETURN_TYPES = ("STRING",) * (CHAIN_STAGE_COUNT + 1)
    RETURN_NAMES = (
        "final_prompt",
        "stage_1",
        "stage_2",
        "stage_3",
        "stage_4",
        "stage_5",
    )
    FUNCTION = "run_chain"
    CATEGORY = "Cyberdelia/Prompt"

    @staticmethod
    def _stage_input(original, previous, handoff_mode):
        if handoff_mode != ORIGINAL_AND_PREVIOUS:
            return previous
        return (
            "Original prompt:\n"
            f"{original}\n\n"
            "Previous stage output:\n"
            f"{previous}"
        )

    @staticmethod
    def _result(final_prompt, stage_outputs):
        padded = list(stage_outputs[:CHAIN_STAGE_COUNT])
        padded.extend([""] * (CHAIN_STAGE_COUNT - len(padded)))
        return (final_prompt, *padded)

    def run_chain(
        self,
        mode,
        text,
        stage_count,
        handoff_mode,
        system_prompt_1,
        system_prompt_2,
        system_prompt_3,
        system_prompt_4,
        system_prompt_5,
        api_url,
        model,
        seed,
        temperature,
        max_tokens,
        timeout,
        keep_terms="",
        preserve_constraints=False,
        clean_output=True,
        error_mode="stop",
        retries=1,
    ):
        original = str(text or "")
        if not mode:
            print("[Prompt Chain] Passthrough mode — using input text unchanged")
            return self._result(original, [])
        if not original.strip():
            print("[Prompt Chain] Empty input text — returning empty prompt")
            return self._result("", [])

        count = min(max(int(stage_count), 1), CHAIN_STAGE_COUNT)
        prompts = [
            system_prompt_1,
            system_prompt_2,
            system_prompt_3,
            system_prompt_4,
            system_prompt_5,
        ][:count]
        normalized_error_mode = str(error_mode or "stop").casefold()
        requested_model = str(model or "").strip() or "auto"

        try:
            resolved_model = resolve_model_name(
                requested_model,
                api_url,
                timeout=timeout,
                require_vision=False,
            )
        except Exception as exc:
            self._log_failure(
                exc,
                api_url,
                requested_model,
                timeout,
                log_label="Prompt Chain",
            )
            if normalized_error_mode == "stop":
                raise RuntimeError(
                    self._failure_message(
                        exc,
                        api_url,
                        requested_model,
                        timeout,
                        feature_name="Prompt Chain",
                    )
                ) from exc
            fallback = "" if normalized_error_mode == "empty" else original
            return self._result(fallback, [])

        current = original
        stage_outputs = []
        for index, system_prompt in enumerate(prompts, start=1):
            instructions = str(system_prompt or "").strip()
            if not instructions:
                print(f"[Prompt Chain] Stage {index} has no system prompt — skipped")
                stage_outputs.append(current)
                continue

            stage_input = (
                original
                if index == 1
                else self._stage_input(original, current, handoff_mode)
            )
            try:
                current = self._generate_final_text(
                    True,
                    stage_input,
                    instructions,
                    api_url,
                    resolved_model,
                    seed,
                    temperature,
                    max_tokens,
                    timeout,
                    keep_terms,
                    preserve_constraints,
                    clean_output,
                    "stop",
                    retries,
                )
            except Exception:
                if normalized_error_mode == "stop":
                    raise
                if normalized_error_mode == "empty":
                    current = ""
                    print(f"[Prompt Chain] Stage {index} failed — returning empty text")
                else:
                    print(
                        f"[Prompt Chain] Stage {index} failed — keeping the previous output"
                    )
            stage_outputs.append(current)

        preview = current[:100].replace("\n", " ")
        print(
            f"[Prompt Chain] Completed {count} stage(s) with '{resolved_model}' "
            f"({len(current)} chars): {preview}..."
        )
        return self._result(current, stage_outputs)
