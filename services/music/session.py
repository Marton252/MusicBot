from __future__ import annotations

from dataclasses import dataclass

from services.music.playback import AudioFilter
from services.music.ui import PlayerUI


class SessionQueueFacade:
    def __init__(self, player) -> None:
        self.player = player

    async def add(self, track: dict, requester: int | None = None) -> bool:
        if requester is not None:
            track["requester_id"] = requester
        return self.player.enqueue(track)

    def clear(self) -> None:
        self.player.queue.clear()


class SessionPlaybackFacade:
    def __init__(self, player) -> None:
        self.player = player

    async def apply_filter(self, audio_filter: AudioFilter) -> None:
        self.player.set_filter(audio_filter.value)

    def skip(self) -> None:
        self.player.skip()

    def stop(self) -> None:
        self.player.stop()


@dataclass(slots=True)
class GuildMusicSession:
    player: object

    def __post_init__(self) -> None:
        self.queue = SessionQueueFacade(self.player)
        self.playback = SessionPlaybackFacade(self.player)
        self.ui = PlayerUI(self.player)

    @property
    def guild_id(self) -> int:
        return self.player.guild.id


class SessionRegistry:
    def for_player(self, player) -> GuildMusicSession:
        return GuildMusicSession(player)

    async def for_guild(self, interaction, cog=None) -> GuildMusicSession:
        from services.player import manager

        player = manager.get_player(interaction, cog=cog)
        return self.for_player(player)


sessions = SessionRegistry()
