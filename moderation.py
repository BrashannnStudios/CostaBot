"""
Comandos de moderación con prefijo ?
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Optional

import discord
from discord.ext import commands

from database import add_warning, clear_warnings, get_warnings
from utils import can_moderate


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    async def _check_mod_perms(
        self, ctx: commands.Context, target: discord.Member
    ) -> bool:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return False
        if not ctx.author.guild_permissions.moderate_members and not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ No tienes permisos de moderación.", delete_after=8)
            return False
        if not can_moderate(ctx.author, target):
            await ctx.send("❌ No puedes moderar a este usuario (jerarquía).", delete_after=8)
            return False
        return True

    def _parse_time(self, time_str: str) -> Optional[timedelta]:
        """Parsea 1h, 30m, 2d, etc."""
        match = re.fullmatch(r"(\d+)([smhd])", time_str.lower())
        if not match:
            return None
        value, unit = int(match.group(1)), match.group(2)
        mapping = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return timedelta(seconds=value * mapping[unit])

    # ──────────────────────────────────────────────
    # Comandos
    # ──────────────────────────────────────────────

    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "Sin razón especificada",
    ):
        if not await self._check_mod_perms(ctx, member):
            return
        try:
            await member.ban(reason=f"{ctx.author}: {reason}")
            await ctx.send(f"🔨 **{member}** ha sido baneado.\nRazón: {reason}")
        except discord.Forbidden:
            await ctx.send("❌ No tengo permisos suficientes para banear a este usuario.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_id: int):
        if not ctx.guild:
            return
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=f"Unban por {ctx.author}")
            await ctx.send(f"✅ **{user}** (`{user_id}`) ha sido desbaneado.")
        except discord.NotFound:
            await ctx.send("❌ Usuario no encontrado o no está baneado.")
        except discord.Forbidden:
            await ctx.send("❌ No tengo permisos para desbanear.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "Sin razón especificada",
    ):
        if not await self._check_mod_perms(ctx, member):
            return
        try:
            await member.kick(reason=f"{ctx.author}: {reason}")
            await ctx.send(f"👢 **{member}** ha sido expulsado.\nRazón: {reason}")
        except discord.Forbidden:
            await ctx.send("❌ No tengo permisos suficientes.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.command(name="timeout", aliases=["mute"])
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout(
        self,
        ctx: commands.Context,
        member: discord.Member,
        time: str,
        *,
        reason: str = "Sin razón especificada",
    ):
        if not await self._check_mod_perms(ctx, member):
            return
        delta = self._parse_time(time)
        if delta is None:
            await ctx.send("❌ Formato de tiempo inválido. Usa: `10m`, `1h`, `2d`, etc.")
            return
        if delta > timedelta(days=28):
            await ctx.send("❌ El timeout máximo es de 28 días.")
            return
        try:
            await member.timeout(delta, reason=f"{ctx.author}: {reason}")
            await ctx.send(
                f"⏱️ **{member}** ha sido silenciado por **{time}**.\nRazón: {reason}"
            )
        except discord.Forbidden:
            await ctx.send("❌ No tengo permisos suficientes.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.command(name="untimeout", aliases=["unmute"])
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def untimeout(self, ctx: commands.Context, member: discord.Member):
        if not await self._check_mod_perms(ctx, member):
            return
        try:
            await member.timeout(None, reason=f"Untimeout por {ctx.author}")
            await ctx.send(f"✅ Se ha quitado el timeout a **{member}**.")
        except discord.Forbidden:
            await ctx.send("❌ No tengo permisos suficientes.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.command(name="warn")
    @commands.has_permissions(moderate_members=True)
    async def warn(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "Sin razón especificada",
    ):
        if not await self._check_mod_perms(ctx, member):
            return
        total = await add_warning(ctx.guild.id, member.id, ctx.author.id, reason)
        await ctx.send(
            f"⚠️ **{member}** ha recibido una advertencia.\n"
            f"Razón: {reason}\n"
            f"Total de warns: **{total}**"
        )

    @commands.command(name="warnings", aliases=["warns"])
    @commands.has_permissions(moderate_members=True)
    async def warnings(self, ctx: commands.Context, member: discord.Member):
        warns = await get_warnings(ctx.guild.id, member.id)
        if not warns:
            await ctx.send(f"**{member}** no tiene advertencias.")
            return

        embed = discord.Embed(
            title=f"Advertencias de {member}",
            color=discord.Color.orange(),
            description=f"Total: **{len(warns)}**",
        )
        from datetime import datetime, timezone

        for w in warns[:10]:  # máximo 10
            mod = ctx.guild.get_member(w["moderator_id"])
            mod_name = mod.display_name if mod else f"ID {w['moderator_id']}"
            dt = datetime.fromtimestamp(w["timestamp"], tz=timezone.utc)
            ts = discord.utils.format_dt(dt, style="R")
            embed.add_field(
                name=f"#{w['id']} • {ts}",
                value=f"**Mod:** {mod_name}\n**Razón:** {w['reason']}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="clear", aliases=["purge"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def clear(self, ctx: commands.Context, cantidad: int):
        if cantidad < 1 or cantidad > 100:
            await ctx.send("❌ La cantidad debe estar entre 1 y 100.")
            return
        deleted = await ctx.channel.purge(limit=cantidad + 1)  # +1 por el comando
        await ctx.send(f"🧹 Se eliminaron **{len(deleted) - 1}** mensajes.", delete_after=5)

    @commands.command(name="lock")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context):
        if not isinstance(ctx.channel, discord.TextChannel):
            return
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("🔒 Canal bloqueado.")

    @commands.command(name="unlock")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context):
        if not isinstance(ctx.channel, discord.TextChannel):
            return
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None  # reset
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("🔓 Canal desbloqueado.")

    @commands.command(name="addrole")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def addrole(
        self, ctx: commands.Context, member: discord.Member, role: discord.Role
    ):
        if role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send("❌ No puedes asignar un rol igual o superior al tuyo.")
            return
        if role >= ctx.guild.me.top_role:
            await ctx.send("❌ Ese rol está por encima de mi rol más alto.")
            return
        try:
            await member.add_roles(role, reason=f"Addrole por {ctx.author}")
            await ctx.send(f"✅ Rol {role.mention} añadido a **{member}**.")
        except discord.Forbidden:
            await ctx.send("❌ No tengo permisos suficientes.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.command(name="removerole")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def removerole(
        self, ctx: commands.Context, member: discord.Member, role: discord.Role
    ):
        if role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send("❌ No puedes quitar un rol igual o superior al tuyo.")
            return
        try:
            await member.remove_roles(role, reason=f"Removerole por {ctx.author}")
            await ctx.send(f"✅ Rol {role.mention} quitado de **{member}**.")
        except discord.Forbidden:
            await ctx.send("❌ No tengo permisos suficientes.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Error: {e}")

    # ──────────────────────────────────────────────
    # Error handlers genéricos
    # ──────────────────────────────────────────────

    @ban.error
    @kick.error
    @timeout.error
    @warn.error
    async def mod_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ No tienes los permisos necesarios.", delete_after=8)
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("❌ Me faltan permisos para ejecutar esa acción.", delete_after=8)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Usuario no encontrado.", delete_after=8)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Argumento inválido.", delete_after=8)
        else:
            await ctx.send(f"❌ Error: {error}", delete_after=10)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
