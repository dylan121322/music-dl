"""Config routes: /api/status, /api/config, /api/config/ai."""
from pathlib import Path

from fastapi import HTTPException

from server_state import CONFIG_PATH, get_api
from server_models import ConfigUpdateRequest, AiConfigRequest
from utils import load_config, save_config, get_platform_status


def register(app):
    @app.get("/api/status")
    def api_status():
        api = get_api()
        config = load_config(CONFIG_PATH)
        return {
            "logged_in": bool(api.g_tk),
            "uin": api.uin if api.g_tk else "",
            "quality": config.get("quality", "320kbps"),
            "download_dir": config.get("download_dir", str(Path.home() / "Music" / "QQMusic")),
            "workers": config.get("workers", 3),
            "has_cookie": bool(config.get("cookie", "")),
            "accounts": get_platform_status(config),
        }

    @app.get("/api/config/ai")
    def api_get_ai_config():
        config = load_config(CONFIG_PATH)
        return {
            "ai_model": config.get("ai_model", ""),
            "ai_model_name": config.get("ai_model_name", ""),
            "ai_key": config.get("ai_key", ""),
            "ai_base_url": config.get("ai_base_url", ""),
        }

    @app.post("/api/config/ai")
    def api_save_ai_config(body: AiConfigRequest):
        config = load_config(CONFIG_PATH)
        config["ai_model"] = body.ai_model
        config["ai_model_name"] = body.ai_model_name
        config["ai_key"] = body.ai_key
        config["ai_base_url"] = body.ai_base_url
        save_config(CONFIG_PATH, config)
        return {"ok": True}

    @app.get("/api/config")
    def api_get_config():
        """Return current user config."""
        return load_config(CONFIG_PATH)

    @app.post("/api/config")
    def api_save_config(body: ConfigUpdateRequest):
        """Save user settings (fixes M3: typed ConfigUpdateRequest replaces raw dict)."""
        config = load_config(CONFIG_PATH)
        if body.quality is not None:
            config["quality"] = body.quality
        if body.download_dir is not None:
            config["download_dir"] = body.download_dir
        if body.workers is not None:
            config["workers"] = body.workers
        save_config(CONFIG_PATH, config)
        return {"ok": True}
