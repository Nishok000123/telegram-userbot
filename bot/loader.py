"""Auto-load plugin modules from bot/plugins."""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database


def load_plugins(client: "TelegramClient", db: "Database", config: "Config") -> None:
    import bot.plugins as plugins_pkg

    loaded: list[str] = []
    for module_info in pkgutil.iter_modules(plugins_pkg.__path__, plugins_pkg.__name__ + "."):
        module = importlib.import_module(module_info.name)
        if hasattr(module, "register"):
            module.register(client, db, config)
            loaded.append(module_info.name.rsplit(".", 1)[-1])

    print(f"Loaded plugins: {', '.join(sorted(loaded))}")
