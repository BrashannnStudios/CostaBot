"""
Sistema de verificación básico con Roblox.
Comprueba que la cuenta tenga al menos N días de antigüedad.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from database import get_guild_config, update_guild_config
from utils import get_roblox_account_age_days, get_roblox_user_id, get_roblox_username, parse_color


class VerifyModal(discord.ui.Modal, title="Verificación Roblox"):
    username = discord.ui.TextInput(
        label="Nombre de usuario de Roblox",
        placeholder="TuUsernameExacto",
        required=True,
        max_length=20,
        min_length=3,
    )

    def __init__(self, cog: "Verify"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Error de contexto.", ephemeral=True)
            return

        username = self.username.value.strip()
        config = await get_guild_config(interaction.guild.id)

        min_days = config.get("verify_min_days", 3)
        verified_role_id = config.get("verified_role_id")
        unverified_role_id = config.get("unverified_role_id")

        if not verified_role_id:
            await interaction.followup.send(
                "El sistema de verificación no está correctamente configurado (falta rol verificado).",
                ephemeral=True,
            )
            return

        # 1. Obtener userId de Roblox
        roblox_id = await get_roblox_user_id(username)
        if roblox_id is None:
            await interaction.followup.send(
                f"No se encontró ningún usuario de Roblox con el nombre **{username}**.\n"
                "Verifica que esté escrito exactamente igual.",
                ephemeral=True,
            )
            return

        # 2. Obtener edad de la cuenta
        age_days = await get_roblox_account_age_days(roblox_id)
        if age_days is None:
            await interaction.followup.send(
                "No se pudo obtener la información de la cuenta de Roblox. Inténtalo más tarde.",
                ephemeral=True,
            )
            return

        if age_days < min_days:
            await interaction.followup.send(
                f"Tu cuenta de Roblox tiene solo **{age_days:.1f} días** de antigüedad.\n"
                f"Se requieren al menos **{min_days} días** para verificarte.",
                ephemeral=True,
            )
            return

        # 3. Roles
        verified_role = interaction.guild.get_role(verified_role_id)
        unverified_role = (
            interaction.guild.get_role(unverified_role_id) if unverified_role_id else None
        )

        if not verified_role:
            await interaction.followup.send(
                "El rol de verificado configurado ya no existe.", ephemeral=True
            )
            return

        member = interaction.user
        try:
            if unverified_role and unverified_role in member.roles:
                await member.remove_roles(unverified_role, reason="Verificación Roblox")
            if verified_role not in member.roles:
                await member.add_roles(verified_role, reason="Verificación Roblox")
        except discord.Forbidden:
            await interaction.followup.send(
                "No tengo permisos suficientes para gestionar roles.", ephemeral=True
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"Error al asignar roles: {e}", ephemeral=True)
            return

        # 4. Cambiar nick (opcional, best-effort)
        real_username = await get_roblox_username(roblox_id) or username
        try:
            await member.edit(nick=real_username[:32], reason="Verificación Roblox")
        except (discord.Forbidden, discord.HTTPException):
            pass  # No crítico

        await interaction.followup.send(
            f"✅ ¡Verificación exitosa!\n"
            f"Cuenta Roblox: **{real_username}** (ID: `{roblox_id}`)\n"
            f"Antigüedad: **{age_days:.1f} días**\n"
            f"Se te ha asignado el rol {verified_role.mention}.",
            ephemeral=True,
        )


class VerifyPanelView(discord.ui.View):
    def __init__(self, cog: "Verify"):
        super().__init__(timeout=None)  # Persistente
        self.cog = cog

    @discord.ui.button(
        label="Verificarme",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="verify:button",
    )
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = VerifyModal(self.cog)
        await interaction.response.send_modal(modal)


class Verify(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Registrar vista persistente
        self.bot.add_view(VerifyPanelView(self))

    @app_commands.command(
        name="verify-setup",
        description="Configura el sistema de verificación con Roblox",
    )
    @app_commands.describe(
        canal="Canal donde se enviará el panel de verificación",
        rol_verificado="Rol que se asignará al verificarse",
        rol_no_verificado="Rol que se quitará al verificarse (opcional)",
        dias_minimos="Días mínimos de antigüedad de la cuenta Roblox (default 3)",
        mensaje="Mensaje del embed del panel",
        color="Color del embed (#hex)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def verify_setup(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        rol_verificado: discord.Role,
        rol_no_verificado: discord.Role | None = None,
        dias_minimos: app_commands.Range[int, 1, 365] = 3,
        mensaje: str = "Haz clic en el botón para verificarte con tu cuenta de Roblox.",
        color: str = "#57F287",
    ):
        if not interaction.guild:
            await interaction.response.send_message(
                "Solo disponible en servidores.", ephemeral=True
            )
            return

        await update_guild_config(
            interaction.guild.id,
            verify_channel_id=canal.id,
            verified_role_id=rol_verificado.id,
            unverified_role_id=rol_no_verificado.id if rol_no_verificado else None,
            verify_min_days=dias_minimos,
            verify_message=mensaje,
            verify_color=color,
        )

        # Enviar / actualizar panel
        embed_color = parse_color(color)
        embed = discord.Embed(
            title="Verificación de cuenta",
            description=mensaje,
            color=embed_color,
        )
        embed.add_field(
            name="Requisitos",
            value=f"• Tener una cuenta de Roblox con al menos **{dias_minimos} días** de antigüedad.",
            inline=False,
        )
        embed.set_footer(text="El bot comprobará la fecha de creación de tu cuenta.")

        view = VerifyPanelView(self)
        try:
            await canal.send(embed=embed, view=view)
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"Configuración guardada, pero no pude enviar el panel: {e}",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"✅ Sistema de verificación configurado.\n"
            f"Panel enviado a {canal.mention}.\n"
            f"Rol verificado: {rol_verificado.mention}\n"
            f"Días mínimos: **{dias_minimos}**",
            ephemeral=True,
        )

    @verify_setup.error
    async def verify_setup_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Necesitas permiso de **Administrador**.", ephemeral=True
            )
        else:
            await interaction.response.send_message(f"Error: {error}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Verify(bot))
