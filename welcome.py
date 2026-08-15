"""
Sistema de bienvenidas con panel de configuración interactivo.
Comando: /welcome-setup
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from database import get_guild_config, update_guild_config
from utils import parse_color, replace_variables


class WelcomeSetupView(discord.ui.View):
    """Panel de configuración con botones Vista previa / Aceptar / Restablecer."""

    def __init__(self, author_id: int, guild_id: int, draft: dict):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.guild_id = guild_id
        self.draft = draft  # copia mutable de la config

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Solo quien ejecutó el comando puede usar este panel.", ephemeral=True
            )
            return False
        return True

    def build_embed(self) -> discord.Embed:
        color = parse_color(self.draft.get("welcome_color", "#5865F2"))
        embed = discord.Embed(
            title="Panel de Configuración – Bienvenidas",
            color=color,
            description=(
                "**Mensaje actual:**\n"
                f"```{self.draft.get('welcome_message', '—')}```\n"
                f"**Color:** `{self.draft.get('welcome_color')}`\n"
                f"**Canal:** <#{self.draft.get('welcome_channel_id')}> "
                f"(`{self.draft.get('welcome_channel_id')}`)\n"
                f"**Imagen:** {self.draft.get('welcome_image') or 'Ninguna'}\n"
                f"**Footer:** `{self.draft.get('welcome_footer')}`\n"
                f"**Canales recomendados:** {self.draft.get('welcome_recommended') or 'Ninguno'}\n"
                f"**Estado:** {'🟢 Activado' if self.draft.get('welcome_enabled') else '🔴 Desactivado'}"
            ),
        )
        embed.set_footer(text="Variables: {user} {user.name} {member-count} {fecha} {server} …")
        return embed

    @discord.ui.button(label="Vista previa", style=discord.ButtonStyle.secondary, emoji="👁️")
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Error de contexto.", ephemeral=True)
            return

        color = parse_color(self.draft.get("welcome_color", "#5865F2"))
        content = replace_variables(self.draft.get("welcome_message", ""), member)
        footer = replace_variables(self.draft.get("welcome_footer", ""), member)

        embed = discord.Embed(description=content, color=color)
        if self.draft.get("welcome_image"):
            embed.set_image(url=self.draft["welcome_image"])
        if footer:
            embed.set_footer(text=footer)

        # Canales recomendados
        recommended = self.draft.get("welcome_recommended") or []
        if recommended:
            channels_text = " • ".join(f"<#{cid}>" for cid in recommended if cid)
            embed.add_field(name="Canales recomendados", value=channels_text, inline=False)

        await interaction.response.send_message(
            content=f"Vista previa para {member.mention}:",
            embed=embed,
            ephemeral=True,
        )

    @discord.ui.button(label="Aceptar", style=discord.ButtonStyle.success, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await update_guild_config(self.guild_id, **self.draft)
        await interaction.response.edit_message(
            content="✅ Configuración de bienvenidas guardada correctamente.",
            embed=None,
            view=None,
        )
        self.stop()

    @discord.ui.button(label="Restablecer", style=discord.ButtonStyle.danger, emoji="🔄")
    async def reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        defaults = {
            "welcome_enabled": 0,
            "welcome_channel_id": None,
            "welcome_message": "¡Bienvenido {user} al servidor!",
            "welcome_color": "#5865F2",
            "welcome_image": None,
            "welcome_footer": "Miembro #{member-count} • {fecha}",
            "welcome_recommended": [],
        }
        self.draft.update(defaults)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class WelcomeSetupModal(discord.ui.Modal, title="Configurar Bienvenidas"):
    """Modal para editar los campos principales."""

    message = discord.ui.TextInput(
        label="Mensaje del embed",
        style=discord.TextStyle.paragraph,
        placeholder="¡Bienvenido {user}! Disfruta el servidor.",
        required=True,
        max_length=2000,
    )
    color = discord.ui.TextInput(
        label="Color del embed (#hex o nombre)",
        placeholder="#5865F2",
        required=False,
        max_length=20,
    )
    footer = discord.ui.TextInput(
        label="Footer (soporta variables)",
        placeholder="Miembro #{member-count} • {fecha}",
        required=False,
        max_length=200,
    )
    image = discord.ui.TextInput(
        label="URL de imagen (opcional)",
        placeholder="https://...",
        required=False,
        max_length=300,
    )
    recommended = discord.ui.TextInput(
        label="IDs de canales recomendados (separados por coma)",
        placeholder="123456789,987654321",
        required=False,
        max_length=200,
    )

    def __init__(self, view: WelcomeSetupView):
        super().__init__()
        self.view_ref = view
        # Pre-llenar con valores actuales
        self.message.default = view.draft.get("welcome_message") or ""
        self.color.default = view.draft.get("welcome_color") or "#5865F2"
        self.footer.default = view.draft.get("welcome_footer") or ""
        self.image.default = view.draft.get("welcome_image") or ""
        rec = view.draft.get("welcome_recommended") or []
        self.recommended.default = ",".join(str(x) for x in rec)

    async def on_submit(self, interaction: discord.Interaction):
        draft = self.view_ref.draft
        draft["welcome_message"] = self.message.value
        draft["welcome_color"] = self.color.value or "#5865F2"
        draft["welcome_footer"] = self.footer.value or ""
        draft["welcome_image"] = self.image.value.strip() or None

        # Parsear canales recomendados
        rec_ids = []
        if self.recommended.value.strip():
            for part in self.recommended.value.split(","):
                part = part.strip()
                if part.isdigit():
                    rec_ids.append(int(part))
        draft["welcome_recommended"] = rec_ids

        await interaction.response.edit_message(
            embed=self.view_ref.build_embed(), view=self.view_ref
        )


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="welcome-setup",
        description="Configura el sistema de bienvenidas del servidor",
    )
    @app_commands.describe(
        canal="Canal donde se enviarán los mensajes de bienvenida",
        activar="Activar o desactivar el sistema",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def welcome_setup(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        activar: bool = True,
    ):
        if not interaction.guild:
            await interaction.response.send_message(
                "Este comando solo funciona en servidores.", ephemeral=True
            )
            return

        config = await get_guild_config(interaction.guild.id)

        # Draft editable
        draft = {
            "welcome_enabled": 1 if activar else 0,
            "welcome_channel_id": canal.id,
            "welcome_message": config.get("welcome_message"),
            "welcome_color": config.get("welcome_color"),
            "welcome_image": config.get("welcome_image"),
            "welcome_footer": config.get("welcome_footer"),
            "welcome_recommended": config.get("welcome_recommended") or [],
        }

        view = WelcomeSetupView(interaction.user.id, interaction.guild.id, draft)

        # Botón extra para abrir el modal de edición
        edit_button = discord.ui.Button(
            label="Editar mensaje / color / footer",
            style=discord.ButtonStyle.primary,
            emoji="✏️",
            row=1,
        )

        async def open_modal(inter: discord.Interaction):
            if inter.user.id != interaction.user.id:
                await inter.response.send_message("No puedes usar este panel.", ephemeral=True)
                return
            modal = WelcomeSetupModal(view)
            await inter.response.send_modal(modal)

        edit_button.callback = open_modal
        view.add_item(edit_button)

        await interaction.response.send_message(
            embed=view.build_embed(),
            view=view,
            ephemeral=True,
        )

    @welcome_setup.error
    async def welcome_setup_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Necesitas permiso de **Administrador** para usar este comando.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"Error: {error}", ephemeral=True
            )

    @commands.Cog.listener()
    async def on_guild_member_add(self, member: discord.Member):
        if member.bot:
            return

        config = await get_guild_config(member.guild.id)
        if not config.get("welcome_enabled"):
            return

        channel_id = config.get("welcome_channel_id")
        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        color = parse_color(config.get("welcome_color", "#5865F2"))
        content = replace_variables(config.get("welcome_message", ""), member)
        footer = replace_variables(config.get("welcome_footer", ""), member)

        embed = discord.Embed(description=content, color=color)
        if config.get("welcome_image"):
            embed.set_image(url=config["welcome_image"])
        if footer:
            embed.set_footer(text=footer)

        recommended = config.get("welcome_recommended") or []
        if recommended:
            channels_text = " • ".join(f"<#{cid}>" for cid in recommended if cid)
            embed.add_field(name="Canales recomendados", value=channels_text, inline=False)

        try:
            await channel.send(content=member.mention, embed=embed)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
