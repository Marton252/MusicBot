from __future__ import annotations

import discord


def can_control(member: discord.Member | discord.User, current_track: dict | None) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.manage_guild:
        return True
    if any(role.name.lower() == "dj" for role in member.roles):
        return True
    return bool(current_track and current_track.get("requester_id") == member.id)


def is_same_voice(interaction: discord.Interaction) -> bool:
    if not interaction.guild or not interaction.guild.voice_client:
        return False
    member = interaction.user
    if not isinstance(member, discord.Member) or not member.voice:
        return False
    return member.voice.channel == interaction.guild.voice_client.channel

