from __future__ import annotations

import discord


def component_id(guild_id: int, action: str) -> str:
    return f"music:{guild_id}:{action}"


class PlayerUI:
    def __init__(self, player) -> None:
        self.player = player

    async def upsert_panel(self, embed: discord.Embed, view: discord.ui.View) -> discord.Message:
        if self.player.np_message:
            try:
                await self.player.np_message.edit(embed=embed, view=view)
                return self.player.np_message
            except (discord.NotFound, discord.HTTPException):
                self.player.np_message = None

        self.player.np_message = await self.player.channel.send(embed=embed, view=view)
        return self.player.np_message

