class CyberdeliaZEngineerInput:
    """Provide shared controls for Cyberdelia Prompt Engineer nodes."""

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
            },
            "optional": {
                "use_vision": ("BOOLEAN", {
                    "default": False,
                    "label_on": "vision image → prompt",
                    "label_off": "normal text → prompt",
                }),
                "active_system_prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Choose a system or Vision preset...",
                }),
            }
        }

    RETURN_TYPES = ("BOOLEAN", "STRING", "BOOLEAN", "STRING")
    RETURN_NAMES = ("mode", "prompt", "use_vision", "active_system_prompt")
    FUNCTION = "route"
    CATEGORY = "Cyberdelia/Prompt"

    def route(self, mode, prompt, use_vision=False, active_system_prompt=""):
        return (mode, prompt, use_vision, active_system_prompt)
