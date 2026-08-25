"""
comfyui-cyberdelia-z-engineer
Cyberdelia Prompt Engineer: model-independent text and vision prompting.
By Cyberdelia AI Lab — https://github.com/cyberdeliaAI
"""

from .z_engineer import CyberdeliaZEngineer
from .z_engineer_input import CyberdeliaZEngineerInput
from .prompt_engineer_text import CyberdeliaPromptEngineerText

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
    "CyberdeliaPromptEngineerText": CyberdeliaPromptEngineerText,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CyberdeliaZEngineer": "Cyberdelia Prompt Engineer — Conditioning",
    "CyberdeliaZEngineerInput": "Cyberdelia Prompt Controls",
    "CyberdeliaPromptEngineerText": "Cyberdelia Prompt Engineer — Text",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
