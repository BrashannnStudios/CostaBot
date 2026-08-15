"""
Utilidades compartidas: variables de plantilla, colores, Roblox API, permisos.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

import aiohttp
import discord


# ──────────────────────────────────────────────
# Variables de bienvenida
# ──────────────────────────────────────────────

VARIABLES = {
    "{user}": lambda m: m.mention,
    "{user.name}": lambda m: m.name,
    "{user.tag}": lambda m: str(m),
    "{user.id}": lambda m: str(m.id),
    "{member-count}": lambda m: str(m.guild.member_count),
    "{server}": lambda m: m.guild.name,
    "{server.id}": lambda m: str(m.guild.id),
    "{fecha}": lambda m: datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"),
    "{fecha.corta}": lambda m: datetime.now(timezone.utc).strftime("%d/%m/%Y"),
}


def replace_variables(text: str, member: discord.Member) -> str:
    """Reemplaza todas las variables conocidas en el texto."""
    if not text:
        return ""
    result = text
    for key, func in VARIABLES.items():
        if key in result:
            try:
                result = result.replace(key, func(member))
            except Exception:
                result = result.replace(key, "N/A")
    return result


def parse_color(value: str) -> discord.Color:
    """Convierte string (#hex o nombre) a discord.Color de forma segura."""
    if not value:
        return discord.Color.blurple()
    value = value.strip()
    if value.startswith("#"):
        try:
            return discord.Color.from_str(value)
        except ValueError:
            return discord.Color.blurple()
    # Nombres comunes
    mapping = {
        "rojo": discord.Color.red(),
        "verde": discord.Color.green(),
        "azul": discord.Color.blue(),
        "amarillo": discord.Color.gold(),
        "naranja": discord.Color.orange(),
        "morado": discord.Color.purple(),
        "rosa": discord.Color.fuchsia(),
        "gris": discord.Color.greyple(),
        "blurple": discord.Color.blurple(),
    }
    return mapping.get(value.lower(), discord.Color.blurple())


# ──────────────────────────────────────────────
# Roblox API
# ──────────────────────────────────────────────

ROBLOX_HEADERS = {
    "User-Agent": "DiscordBot/1.0 (Verification System)",
    "Accept": "application/json",
}


async def get_roblox_user_id(username: str) -> Optional[int]:
    """Obtiene el userId de Roblox a partir del username."""
    url = "https://users.roblox.com/v1/usernames/users"
    payload = {"usernames": [username], "excludeBannedUsers": True}

    async with aiohttp.ClientSession(headers=ROBLOX_HEADERS) as session:
        async with session.post(url, json=payload, timeout=10) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            users = data.get("data", [])
            if not users:
                return None
            return users[0].get("id")


async def get_roblox_account_age_days(user_id: int) -> Optional[float]:
    """
    Devuelve la edad de la cuenta en días (float).
    None si falla la consulta.
    """
    url = f"https://users.roblox.com/v1/users/{user_id}"

    async with aiohttp.ClientSession(headers=ROBLOX_HEADERS) as session:
        async with session.get(url, timeout=10) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            created_str = data.get("created")
            if not created_str:
                return None
            # Formato ISO 8601 de Roblox
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta = now - created
            return delta.total_seconds() / 86400.0


async def get_roblox_username(user_id: int) -> Optional[str]:
    """Devuelve el username actual de un userId de Roblox."""
    url = f"https://users.roblox.com/v1/users/{user_id}"

    async with aiohttp.ClientSession(headers=ROBLOX_HEADERS) as session:
        async with session.get(url, timeout=10) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get("name")


# ──────────────────────────────────────────────
# Helpers de moderación / permisos
# ──────────────────────────────────────────────

def can_moderate(moderator: discord.Member, target: discord.Member) -> bool:
    """Comprueba hierarchy + que no sea el owner."""
    if target.id == moderator.guild.owner_id:
        return False
    if moderator.id == moderator.guild.owner_id:
        return True
    return moderator.top_role > target.top_role


INVITE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discordapp\.com/invite)/[a-zA-Z0-9]+",
    re.IGNORECASE,
)


def contains_invite(content: str) -> bool:
    return bool(INVITE_REGEX.search(content))
