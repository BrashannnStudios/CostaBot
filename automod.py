"""
Sistema AutoMOD: detección de flood y spam de invitaciones.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque

import discord
from discord import app_commands
from discord.ext import commands

from database import add_warning, get_guild_config, update_guild_config
from utils import contains_invite


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # user_id -> deque de (timestamp, content)
        self.message_history: dict[int, Deque[tuple[float, str]]] = defaultdict(
            lambda: deque(maxlen=20)
        )

    @app_commands.command(
        name="automod-setup",
        description="Configura el sistema de AutoMOD del servidor",
    )
    @app_commands.describe(
        canal_logs="Canal donde se enviarán los logs de sanciones automáticas",
        activar="Activar o desactivar AutoMOD",
        flood_mensajes="Cantidad de mensajes repetidos para detectar flood (default 4)",
        flood_segundos="Ventana de tiempo en segundos (default 5)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_setup(
        self,
        interaction: discord.Interaction,
        canal_logs: discord.TextChannel,
        activar: bool = True,
        flood_mensajes: app_commands.Range[int, 3, 10] = 4,
        flood_segundos: app_commands.Range[int, 3, 15] = 5,
    ):
        if not interaction.guild:
            await interaction.response.send_message(
                "Solo disponible en servidores.", ephemeral=True
            )
            return

        await update_guild_config(
            interaction.guild.id,
            automod_enabled=1 if activar else 0,
            automod_log_channel=canal_logs.id,
            automod_flood_count=flood_mensajes,
            automod_flood_seconds=flood_segundos,
        )

        embed = discord.Embed(
            title="AutoMOD configurado",
            color=discord.Color.green() if activar else discord.Color.red(),
            description=(
                f"**Estado:** {'🟢 Activado' if activar else '🔴 Desactivado'}\n"
                f"**Canal de logs:** {canal_logs.mention}\n"
                f"**Flood:** {flood_mensajes} mensajes idénticos en ≤ {flood_segundos}s\n"
                f"**Spam de invites:** Elimina + advertencia\n"
                f"**Lógica de warns:** 3 advertencias automáticas = 1 warn formal"
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @automod_setup.error
    async def automod_setup_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Necesitas permiso de **Administrador**.", ephemeral=True
            )
        else:
            await interaction.response.send_message(f"Error: {error}", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not isinstance(message.author, discord.Member):
            return

        # Ignorar moderadores
        if message.author.guild_permissions.manage_messages:
            return

        config = await get_guild_config(message.guild.id)
        if not config.get("automod_enabled"):
            return

        # ── Detección de invites ──────────────────────────────────────
        if contains_invite(message.content):
            try:
                await message.delete()
            except discord.HTTPException:
                pass

            await self._apply_automod_action(
                message,
                config,
                reason="Envío de invitación de Discord (spam)",
                action_type="invite",
            )
            return

        # ── Detección de flood ────────────────────────────────────────
        now = time.time()
        uid = message.author.id
        history = self.message_history[uid]
        history.append((now, message.content.strip().lower()))

        flood_count = config.get("automod_flood_count", 4)
        flood_seconds = config.get("automod_flood_seconds", 5)

        # Contar mensajes idénticos en la ventana de tiempo
        recent = [
            (ts, content)
            for ts, content in history
            if now - ts <= flood_seconds
        ]
        if len(recent) >= flood_count:
            # Verificar si son el mismo contenido
            contents = [c for _, c in recent]
            if len(set(contents)) == 1 and contents[0]:
                # Flood detectado → borrar los mensajes recientes del usuario
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass

                # Intentar borrar los anteriores (best-effort)
                async for msg in message.channel.history(limit=15):
                    if (
                        msg.author.id == uid
                        and msg.content.strip().lower() == contents[0]
                        and (now - msg.created_at.timestamp()) <= flood_seconds + 1
                    ):
                        try:
                            await msg.delete()
                        except discord.HTTPException:
                            pass

                await self._apply_automod_action(
                    message,
                    config,
                    reason=f"Flood: {flood_count}+ mensajes idénticos en ≤{flood_seconds}s",
                    action_type="flood",
                )
                # Limpiar historial del usuario para evitar spam de acciones
                history.clear()

    async def _apply_automod_action(
        self,
        message: discord.Message,
        config: dict,
        reason: str,
        action_type: str,
    ):
        """Aplica advertencia automática y log."""
        guild = message.guild
        author = message.author
        assert guild and isinstance(author, discord.Member)

        # Contador interno de advertencias automáticas (usamos el sistema de warns)
        total_warns = await add_warning(
            guild.id,
            author.id,
            self.bot.user.id if self.bot.user else 0,
            f"[AutoMOD] {reason}",
        )

        # Mensaje al usuario
        try:
            warn_msg = (
                f"Hey {author.mention}! Nuestro sistema detectó **{action_type}** de tu parte.\n"
                f"Fuiste advertido automáticamente y se eliminaron los mensajes.\n"
                f"**Advertencias totales:** {total_warns}\n"
                f"*(3 advertencias = 1 warn formal registrado)*"
            )
            await message.channel.send(warn_msg, delete_after=12)
        except discord.HTTPException:
            pass

        # Log
        log_channel_id = config.get("automod_log_channel")
        if log_channel_id:
            log_ch = guild.get_channel(log_channel_id)
            if isinstance(log_ch, discord.TextChannel):
                embed = discord.Embed(
                    title="AutoMOD – Acción automática",
                    color=discord.Color.orange(),
                    timestamp=discord.utils.utcnow(),
                )
                embed.add_field(name="Usuario", value=f"{author} (`{author.id}`)", inline=True)
                embed.add_field(name="Tipo", value=action_type.upper(), inline=True)
                embed.add_field(name="Razón", value=reason, inline=False)
                embed.add_field(name="Warns totales", value=str(total_warns), inline=True)
                embed.set_footer(text=f"Canal: #{message.channel.name}")
                try:
                    await log_ch.send(embed=embed)
                except discord.HTTPException:
                    pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
