"""
comfyui-cyberdelia-z-engineer
LLM-powered prompt engineering node for Z-Image Turbo workflows.
By Cyberdelia AI Lab — https://github.com/cyberdeliaAI
"""

from .z_engineer import CyberdeliaZEngineer

NODE_CLASS_MAPPINGS = {
    "CyberdeliaZEngineer": CyberdeliaZEngineer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CyberdeliaZEngineer": "Cyberdelia Z-Engineer",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
