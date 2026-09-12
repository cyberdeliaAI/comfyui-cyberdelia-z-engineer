"""
comfyui-cyberdelia-z-engineer
Cyberdelia Prompt Engineer: model-independent text, vision, and Danbooru prompting.
By Cyberdelia AI Lab — https://github.com/cyberdeliaAI
"""

from .z_engineer import CyberdeliaZEngineer
from .z_engineer_input import CyberdeliaZEngineerInput
from .prompt_preset_controls import CyberdeliaPromptPresetControls
from .prompt_engineer_text import CyberdeliaPromptEngineerText
from .danbooru_node import CyberdeliaDanbooruPrompt
from .image_loader import CyberdeliaVisionImageLoader

WEB_DIRECTORY = "./web"

try:
    from .server_routes import register_routes

    register_routes()
except (ImportError, AttributeError, RuntimeError) as exc:
    # Importing the package outside ComfyUI (for example in unit tests) does
    # not provide PromptServer. The core node remains usable without the
    # optional model/preset dropdown helpers.
    import logging

    logging.debug("Prompt Engineer frontend routes were not registered: %s", exc)

NODE_CLASS_MAPPINGS = {
    # Keep both legacy IDs stable so existing workflows continue to load.
    "CyberdeliaZEngineer": CyberdeliaZEngineer,
    "CyberdeliaZEngineerInput": CyberdeliaZEngineerInput,
    "CyberdeliaPromptPresetControls": CyberdeliaPromptPresetControls,
    "CyberdeliaPromptEngineerText": CyberdeliaPromptEngineerText,
    "CyberdeliaDanbooruPrompt": CyberdeliaDanbooruPrompt,
    "CyberdeliaVisionImageLoader": CyberdeliaVisionImageLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CyberdeliaZEngineer": "Cyberdelia Prompt Engineer — Conditioning",
    "CyberdeliaZEngineerInput": "Cyberdelia Prompt Controls",
    "CyberdeliaPromptPresetControls": "Cyberdelia Prompt Controls — Presets",
    "CyberdeliaPromptEngineerText": "Cyberdelia Prompt Engineer — Text",
    "CyberdeliaDanbooruPrompt": "Cyberdelia Danbooru Prompt",
    "CyberdeliaVisionImageLoader": "Cyberdelia Vision Image Loader",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
