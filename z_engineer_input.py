class CyberdeliaZEngineerInput:
    """Provide a shared mode toggle and prompt for a Z-Engineer node."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": ("BOOLEAN", {
                    "default": True,
                    "label_on": "✨ engineered (LLM)",
                    "label_off": "→ passthrough (raw)",
                }),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Enter your prompt here...",
                }),
            }
        }

    RETURN_TYPES = ("BOOLEAN", "STRING")
    RETURN_NAMES = ("mode", "prompt")
    FUNCTION = "route"
    CATEGORY = "Cyberdelia/Prompt"

    def route(self, mode, prompt):
        return (mode, prompt)
