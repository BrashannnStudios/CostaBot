"""
Punto de entrada del bot.
Incluye keep-alive HTTP para Render free tier.
"""

from __future__ import annotations

import asyncio
import logging
import os
from aiohttp import web

import discord
from discord.ext import commands
from dotenv import load_dotenv

from database import init_db

load_dotenv()

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s → %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bot")

# ──────────────────────────────────────────────
# Intents
# ──────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True          # Privileged – necesario para AutoMOD y prefix
intents.members = True                  # Privileged – necesario para welcome + verify
intents.guilds = True


class Bot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix="?",
            intents=intents,
            help_command=None,
            case_insensitive=True,
        )

    async def setup_hook(self) -> None:
        await init_db()
        log.info("Base de datos inicializada")

        # Cargar cogs (archivos planos)
        extensions = [
            "welcome",
            "automod",
            "verify",
            "moderation",
        ]
        for ext in extensions:
            try:
                await self.load_extension(ext)
                log.info(f"Extensión cargada: {ext}")
            except Exception as e:
                log.exception(f"Error cargando {ext}: {e}")

        # Sincronizar slash commands
        try:
            synced = await self.tree.sync()
            log.info(f"Slash commands sincronizados: {len(synced)}")
        except Exception as e:
            log.exception(f"Error sincronizando comandos: {e}")

    async def on_ready(self) -> None:
        log.info(f"Conectado como {self.user} (ID: {self.user.id})")
        log.info(f"Servidores: {len(self.guilds)}")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="?help | /welcome-setup",
            )
        )


bot = Bot()


# ──────────────────────────────────────────────
# Keep-alive para Render (free tier)
# ──────────────────────────────────────────────
async def health_handler(request: web.Request) -> web.Response:
    return web.json_response({"status": "online", "bot": str(bot.user)})


async def start_web_server() -> None:
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)

    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info(f"Keep-alive escuchando en puerto {port}")


async def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Falta la variable de entorno DISCORD_TOKEN")

    # Arrancar keep-alive y bot en paralelo
    await asyncio.gather(
        start_web_server(),
        bot.start(token),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot detenido manualmente")
