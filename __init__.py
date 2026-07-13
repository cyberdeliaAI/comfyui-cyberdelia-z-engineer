"""
comfyui-cyberdelia-z-engineer
Model-independent LLM-powered prompt engineering node for ComfyUI.
By Cyberdelia AI Lab — https://github.com/cyberdeliaAI
"""

from .z_engineer import CyberdeliaZEngineer

WEB_DIRECTORY = "./web"

try:
    from .server_routes import register_routes

    register_routes()
except (ImportError, AttributeError, RuntimeError) as exc:
    # Importing the package outside ComfyUI (for example in unit tests) does
    # not provide PromptServer. The core node remains usable without the
    # optional model/preset dropdown helpers.
    import logging

    logging.debug("Z-Engineer frontend routes were not registered: %s", exc)

NODE_CLASS_MAPPINGS = {
    "CyberdeliaZEngineer": CyberdeliaZEngineer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CyberdeliaZEngineer": "Cyberdelia Z-Engineer",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
