"""Preset-aware companion controls for Cyberdelia Prompt Engineer nodes."""

from copy import deepcopy

from .z_engineer_input import CyberdeliaZEngineerInput


class CyberdeliaPromptPresetControls(CyberdeliaZEngineerInput):
    """Route shared controls plus the active system or Vision instructions."""

    @classmethod
    def INPUT_TYPES(cls):
        inputs = deepcopy(super().INPUT_TYPES())
        inputs["optional"]["active_system_prompt"] = ("STRING", {
            "multiline": True,
            "default": "",
            "placeholder": "Choose a system or Vision preset...",
        })
        return inputs

    RETURN_TYPES = ("BOOLEAN", "STRING", "BOOLEAN", "STRING")
    RETURN_NAMES = ("mode", "prompt", "use_vision", "active_system_prompt")

    def route(self, mode, prompt, use_vision=False, active_system_prompt=""):
        return (mode, prompt, use_vision, active_system_prompt)
