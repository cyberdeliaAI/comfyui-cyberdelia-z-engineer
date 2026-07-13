"""Small HTTP endpoints used by the optional ComfyUI frontend helpers."""

import asyncio
import logging

from .model_utils import discover_models
from .preset_manager import get_user_preset_dir, list_presets


_ROUTES_REGISTERED = False


def register_routes():
    global _ROUTES_REGISTERED
    if _ROUTES_REGISTERED:
        return

    from aiohttp import web
    from server import PromptServer

    routes = PromptServer.instance.routes

    @routes.get("/cyberdelia/z-engineer/models")
    async def zengineer_models(request):
        api_url = request.query.get("api_url", "http://localhost:1234/v1")
        force = request.query.get("force", "0").casefold() in {"1", "true", "yes"}
        try:
            models = await asyncio.to_thread(
                discover_models,
                api_url,
                2.0,
                force,
            )
            return web.json_response({"models": models})
        except Exception as exc:
            logging.warning("Z-Engineer model discovery failed: %s", exc)
            return web.json_response({"error": str(exc), "models": []}, status=502)

    @routes.get("/cyberdelia/z-engineer/presets")
    async def zengineer_presets(_request):
        try:
            presets = await asyncio.to_thread(list_presets, True)
            user_directory = get_user_preset_dir(create=False)
            return web.json_response(
                {
                    "presets": presets,
                    "user_directory": str(user_directory) if user_directory else None,
                }
            )
        except Exception as exc:
            logging.warning("Z-Engineer preset discovery failed: %s", exc)
            return web.json_response({"error": str(exc), "presets": []}, status=500)

    _ROUTES_REGISTERED = True
