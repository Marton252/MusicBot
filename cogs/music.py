from __future__ import annotations

import asyncio
import datetime
import logging
import os
import re

import discord
from discord import app_commands
from discord.ext import commands

from config import MAX_QUEUE_SIZE
from services.extractor import YTDLSource, is_playlist_url, _detect_platform
from services.language import language
from services.lyrics import lyrics_service
from services.music.playback import AudioFilter
from services.music.policies import can_control as policy_can_control
from services.music.policies import is_same_voice as policy_is_same_voice
from services.music.queue import QueueItem
from services.music.session import sessions
from services.music.ui import component_id
from services.player import MusicPlayer, manager

logger = logging.getLogger('MusicBot.Music')

# Pre-compiled regex patterns for title cleaning
_RE_BRACKETS = re.compile(r'\(.*?\)|\[.*?\]')
_RE_SPLIT_DELIM = re.compile(r'\||//| - Topic|\s{2,}')
_RE_SUFFIX = re.compile(r'(?i)\s*(official\s?(?:video|music(?:\s?video)?|audio)?|lyric(?:s)?\s?(?:video)?|live(?:\s?performance)?)\b')
_RE_VEVO = re.compile(r'(?i)(?:vevo| - topic|\s*official\b.*)$')

# Seconds before transient feedback messages are auto-deleted
_FEEDBACK_DELETE_AFTER = 10


def _schedule_delete(msg: discord.Message, delay: float = _FEEDBACK_DELETE_AFTER) -> None:
    """Schedule a message for deletion after *delay* seconds.

    Uses ``asyncio.create_task`` so the coroutine is never silently dropped.
    """
    async def _do_delete() -> None:
        await asyncio.sleep(delay)
        try:
            await msg.delete()
        except (discord.NotFound, discord.HTTPException):
            pass
    asyncio.create_task(_do_delete())

# ────────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────────

def _format_duration(seconds: int | float) -> str:
    """Format seconds into mm:ss or h:mm:ss."""
    seconds = int(seconds)
    if seconds <= 0:
        return "Live"
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def _clean_song_title(track: dict) -> str:
    """Sanitize the track title and intelligently append uploader for Genius lookups."""
    title = track.get('title', '')
    
    # Strip (Official Video), [Audio], [Official Lyric Video], etc.
    title = _RE_BRACKETS.sub('', title)
    
    # Strip common trailing suffixes outside brackets, and double spaces which often denote fluff
    title = _RE_SPLIT_DELIM.split(title)[0].strip()
    title = _RE_SUFFIX.sub('', title).strip()
    
    # If the cleaned title already contains a dash, it's very likely "Artist - Title"
    if '-' in title:
        return title
        
    uploader = track.get('uploader', '')
    if uploader:
        # Avoid prepending useless network uploaders
        if not uploader.lower().endswith('vevo'):
            uploader = _RE_VEVO.sub('', uploader).strip()
            # Prevent "Artist Artist - Title"
            if uploader.lower() not in title.lower():
                return f"{uploader} {title}"
                
    return title

def _can_control(interaction: discord.Interaction, player: MusicPlayer) -> bool:
    """Check if the user can control the player.

    Allowed: server admins (manage_guild), members with a role named 'DJ',
    or the person who queued the current track.
    """
    return policy_can_control(interaction.user, player.current)


def _is_same_voice(interaction: discord.Interaction) -> bool:
    """Return True when the member is in the bot's active voice channel."""
    return policy_is_same_voice(interaction)


async def _require_player_control(
    interaction: discord.Interaction,
    player: MusicPlayer | None,
    *,
    require_current: bool = True,
) -> bool:
    """Shared guard for slash-command playback controls."""
    if not player or (require_current and not player.current):
        msg = await language.get_string(interaction.guild_id, "msg_no_playing")
        await interaction.response.send_message(msg, ephemeral=True)
        return False

    if not _can_control(interaction, player):
        msg = await language.get_string(interaction.guild_id, "msg_no_permission")
        await interaction.response.send_message(msg, ephemeral=True)
        return False

    if not _is_same_voice(interaction):
        msg = await language.get_string(interaction.guild_id, "msg_error_same_voice_required")
        await interaction.response.send_message(msg, ephemeral=True)
        return False

    return True


async def _build_queue_embed(
    player: MusicPlayer, guild_id: int, embed_color: int = 0x8000FF,
) -> discord.Embed:
    """Build the queue embed — shared by the button callback and the /queue command."""
    if not player.queue:
        msg = await language.get_string(guild_id, "msg_queue_empty")
        return discord.Embed(description=msg, color=embed_color)

    q_list = list(player.queue)
    desc = "\n".join(f"{i}. {song['title']}" for i, song in enumerate(q_list[:10], 1))
    if len(q_list) > 10:
        more = await language.get_string(guild_id, "emb_queue_more", count=len(q_list) - 10)
        desc += more

    title_msg = await language.get_string(guild_id, "emb_queue_title")
    return discord.Embed(title=title_msg, description=desc, color=embed_color)


async def _build_np_embed(player: MusicPlayer, guild_id: int) -> discord.Embed:
    """Build the rich now-playing embed."""
    track = player.current
    if not track:
        return discord.Embed(description="Nothing playing.")

    keys = [
        "emb_np_title", "emb_np_artist", "emb_np_duration",
        "emb_np_platform", "emb_np_status",
        "emb_np_status_playing", "emb_np_status_paused", "emb_np_footer",
    ]
    vals = await asyncio.gather(*(language.get_string(guild_id, k) for k in keys))
    s = dict(zip(keys, vals))

    embed = discord.Embed(
        title=s["emb_np_title"],
        description=f"[{track['title']}]({track['webpage_url']})",
        color=player.bot.embed_color if hasattr(player.bot, 'embed_color') else 0x8000FF,
        timestamp=datetime.datetime.now(datetime.UTC),
    )

    platform = _detect_platform(track)

    embed.add_field(name=s["emb_np_artist"], value=track.get("uploader", "Unknown"), inline=True)
    embed.add_field(name=s["emb_np_duration"], value=_format_duration(track.get("duration", 0)), inline=True)
    embed.add_field(name=s["emb_np_platform"], value=platform, inline=True)

    status_text = s["emb_np_status_paused"] if player.paused else s["emb_np_status_playing"]
    embed.add_field(name=s["emb_np_status"], value=status_text, inline=False)

    embed.set_footer(text=s["emb_np_footer"])

    if track.get("thumbnail"):
        embed.set_thumbnail(url=track["thumbnail"])

    return embed


async def _build_np_view(player: MusicPlayer, guild_id: int) -> MusicControlView:
    """Build the button view with localized labels."""
    keys = [
        "btn_pause", "btn_resume", "btn_skip", "btn_stop", "btn_queue",
        "btn_shuffle", "btn_volume", "btn_repeat_off", "btn_repeat_on",
        "btn_lyrics", "btn_report", "btn_filter",
    ]
    vals = await asyncio.gather(*(language.get_string(guild_id, k) for k in keys))
    s = dict(zip(keys, vals))

    return MusicControlView(
        guild_id=guild_id,
        is_paused=player.paused,
        is_repeat=player.repeat,
        labels=s,
    )


# ────────────────────────────────────────────────────────────────────────────────
# Volume Select Menu
# ────────────────────────────────────────────────────────────────────────────────

class VolumeSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label="10%", value="10", emoji="🔈"),
            discord.SelectOption(label="25%", value="25", emoji="🔉"),
            discord.SelectOption(label="50%", value="50", emoji="🔉"),
            discord.SelectOption(label="75%", value="75", emoji="🔊"),
            discord.SelectOption(label="100%", value="100", emoji="🔊", default=True),
            discord.SelectOption(label="125%", value="125", emoji="🔊"),
            discord.SelectOption(label="150%", value="150", emoji="📢"),
        ]
        super().__init__(placeholder="🔊 Volume", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not player or not _can_control(interaction, player):
            msg = await language.get_string(interaction.guild_id, "msg_no_permission")
            return await interaction.response.send_message(msg, ephemeral=True)

        vol = int(self.values[0])
        player.set_volume(vol / 100)

        msg = await language.get_string(interaction.guild_id, "msg_volume_set", volume=vol)
        await interaction.response.send_message(msg, ephemeral=True, delete_after=_FEEDBACK_DELETE_AFTER)


class VolumeView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=30)
        self.add_item(VolumeSelect())


# ────────────────────────────────────────────────────────────────────────────────
# Filter Select Menu
# ────────────────────────────────────────────────────────────────────────────────

class FilterSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label="None", value="none", emoji="🔇", description="No filter"),
            discord.SelectOption(label="Bassboost", value="bassboost", emoji="🔉", description="Heavy bass boost"),
            discord.SelectOption(label="Nightcore", value="nightcore", emoji="🎵", description="Speed up + pitch raise"),
            discord.SelectOption(label="Vaporwave", value="vaporwave", emoji="🌊", description="Slow down + pitch lower"),
            discord.SelectOption(label="Karaoke", value="karaoke", emoji="🎤", description="Reduce centered vocals"),
            discord.SelectOption(label="8D", value="8d", emoji="🌀", description="Panning spatial effect"),
        ]
        super().__init__(placeholder="🎛️ Select a filter", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not player or not _can_control(interaction, player):
            msg = await language.get_string(interaction.guild_id, "msg_no_permission")
            return await interaction.response.send_message(msg, ephemeral=True)

        filter_name = self.values[0]
        display = filter_name.capitalize() if filter_name != "none" else "None"
        player.set_filter(filter_name)

        msg = await language.get_string(interaction.guild_id, "msg_filters_applied", filter=display)
        await interaction.response.send_message(msg, ephemeral=True, delete_after=_FEEDBACK_DELETE_AFTER)


class FilterView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=30)
        self.add_item(FilterSelect())


# ────────────────────────────────────────────────────────────────────────────────
# Report Modal — reuse the one from general.py (DRY)
# ────────────────────────────────────────────────────────────────────────────────

from cogs.general import _show_report_modal, _try_report_emoji


class PersistentMusicReportView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(custom_id="persistent_music_report")
    async def on_report_click(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await _show_report_modal(interaction)


# ────────────────────────────────────────────────────────────────────────────────
# Music Control View (Buttons)
# ────────────────────────────────────────────────────────────────────────────────

class MusicControlView(discord.ui.View):
    def __init__(
        self,
        guild_id: int,
        is_paused: bool = False,
        is_repeat: bool = False,
        labels: dict[str, str] | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self.guild_id = guild_id
        lb = labels or {}

        # Row 0: Pause/Resume, Skip, Stop, Queue, Shuffle
        pause_label = lb.get("btn_resume", "Resume") if is_paused else lb.get("btn_pause", "Pause")
        pause_emoji = "▶️" if is_paused else "⏸️"

        self.pause_btn = discord.ui.Button(
            label=pause_label, emoji=pause_emoji,
            style=discord.ButtonStyle.secondary, row=0,
            custom_id=component_id(guild_id, "pause"),
        )
        self.pause_btn.callback = self.on_pause
        self.add_item(self.pause_btn)

        self.skip_btn = discord.ui.Button(
            label=lb.get("btn_skip", "Skip"), emoji="⏭️",
            style=discord.ButtonStyle.secondary, row=0,
            custom_id=component_id(guild_id, "skip"),
        )
        self.skip_btn.callback = self.on_skip
        self.add_item(self.skip_btn)

        self.stop_btn = discord.ui.Button(
            label=lb.get("btn_stop", "Stop"), emoji="⏹️",
            style=discord.ButtonStyle.danger, row=0,
            custom_id=component_id(guild_id, "stop"),
        )
        self.stop_btn.callback = self.on_stop
        self.add_item(self.stop_btn)

        self.queue_btn = discord.ui.Button(
            label=lb.get("btn_queue", "Queue"), emoji="📋",
            style=discord.ButtonStyle.primary, row=0,
            custom_id=component_id(guild_id, "queue"),
        )
        self.queue_btn.callback = self.on_queue
        self.add_item(self.queue_btn)

        self.shuffle_btn = discord.ui.Button(
            label=lb.get("btn_shuffle", "Shuffle"), emoji="🔀",
            style=discord.ButtonStyle.secondary, row=0,
            custom_id=component_id(guild_id, "shuffle"),
        )
        self.shuffle_btn.callback = self.on_shuffle
        self.add_item(self.shuffle_btn)

        # Row 1: Volume, Repeat, Filter, Lyrics, Report
        self.volume_btn = discord.ui.Button(
            label=lb.get("btn_volume", "Volume"), emoji="🔊",
            style=discord.ButtonStyle.secondary, row=1,
            custom_id=component_id(guild_id, "volume"),
        )
        self.volume_btn.callback = self.on_volume
        self.add_item(self.volume_btn)

        repeat_label = lb.get("btn_repeat_on", "Repeat: On") if is_repeat else lb.get("btn_repeat_off", "Repeat: Off")
        self.repeat_btn = discord.ui.Button(
            label=repeat_label, emoji="🔁",
            style=discord.ButtonStyle.success if is_repeat else discord.ButtonStyle.secondary,
            row=1,
            custom_id=component_id(guild_id, "repeat"),
        )
        self.repeat_btn.callback = self.on_repeat
        self.add_item(self.repeat_btn)

        self.filter_btn = discord.ui.Button(
            label=lb.get("btn_filter", "Filter"), emoji="🎛️",
            style=discord.ButtonStyle.secondary, row=1,
            custom_id=component_id(guild_id, "filter"),
        )
        self.filter_btn.callback = self.on_filter
        self.add_item(self.filter_btn)

        self.lyrics_btn = discord.ui.Button(
            label=lb.get("btn_lyrics", "Lyrics"), emoji="📜",
            style=discord.ButtonStyle.secondary, row=1,
            custom_id=component_id(guild_id, "lyrics"),
        )
        self.lyrics_btn.callback = self.on_lyrics
        self.add_item(self.lyrics_btn)

        self.report_btn = discord.ui.Button(
            label=lb.get("btn_report", "Report"),
            emoji=_try_report_emoji(),
            style=discord.ButtonStyle.danger, row=1,
            custom_id=component_id(guild_id, "report")
        )
        self.report_btn.callback = self.on_report
        self.add_item(self.report_btn)

    # ── Button Callbacks ──────────────────────────────────────────────────

    async def on_pause(self, interaction: discord.Interaction) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not player or not _can_control(interaction, player):
            msg = await language.get_string(interaction.guild_id, "msg_no_permission")
            return await interaction.response.send_message(msg, ephemeral=True)

        if player.paused:
            player.resume()
            msg = await language.get_string(interaction.guild_id, "msg_resumed")
        else:
            player.pause()
            msg = await language.get_string(interaction.guild_id, "msg_paused")

        # Update the embed and view to reflect new state
        embed = await _build_np_embed(player, interaction.guild_id)
        view = await _build_np_view(player, interaction.guild_id)
        await interaction.response.edit_message(embed=embed, view=view)

    async def on_skip(self, interaction: discord.Interaction) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not player or not _can_control(interaction, player):
            msg = await language.get_string(interaction.guild_id, "msg_no_permission")
            return await interaction.response.send_message(msg, ephemeral=True)

        player.skip()
        msg = await language.get_string(interaction.guild_id, "msg_skipped")
        await interaction.response.send_message(msg, ephemeral=True, delete_after=_FEEDBACK_DELETE_AFTER)

    async def on_stop(self, interaction: discord.Interaction) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not player or not _can_control(interaction, player):
            msg = await language.get_string(interaction.guild_id, "msg_no_permission")
            return await interaction.response.send_message(msg, ephemeral=True)

        player.stop()
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()


        # Disable all buttons except report
        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                if item is not self.report_btn:
                    item.disabled = True
        await interaction.response.edit_message(view=self)

    async def on_queue(self, interaction: discord.Interaction) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not player or not player.queue:
            msg = await language.get_string(interaction.guild_id, "msg_queue_empty")
            return await interaction.response.send_message(msg, ephemeral=True, delete_after=_FEEDBACK_DELETE_AFTER)

        color = player.bot.embed_color if hasattr(player.bot, 'embed_color') else 0x8000FF
        embed = await _build_queue_embed(player, interaction.guild_id, color)
        await interaction.response.send_message(embed=embed, ephemeral=True, delete_after=30)

    async def on_shuffle(self, interaction: discord.Interaction) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not player or not _can_control(interaction, player):
            msg = await language.get_string(interaction.guild_id, "msg_no_permission")
            return await interaction.response.send_message(msg, ephemeral=True)

        player.shuffle()
        msg = await language.get_string(interaction.guild_id, "msg_shuffled")
        await interaction.response.send_message(msg, ephemeral=True, delete_after=_FEEDBACK_DELETE_AFTER)

    async def on_volume(self, interaction: discord.Interaction) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not player or not _can_control(interaction, player):
            msg = await language.get_string(interaction.guild_id, "msg_no_permission")
            return await interaction.response.send_message(msg, ephemeral=True)

        await interaction.response.send_message(view=VolumeView(), ephemeral=True, delete_after=30)

    async def on_repeat(self, interaction: discord.Interaction) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not player or not _can_control(interaction, player):
            msg = await language.get_string(interaction.guild_id, "msg_no_permission")
            return await interaction.response.send_message(msg, ephemeral=True)

        is_on = player.toggle_repeat()
        key = "msg_repeat_on" if is_on else "msg_repeat_off"
        msg = await language.get_string(interaction.guild_id, key)

        # Update the embed and view to reflect new state
        embed = await _build_np_embed(player, interaction.guild_id)
        view = await _build_np_view(player, interaction.guild_id)
        await interaction.response.edit_message(embed=embed, view=view)

    async def on_filter(self, interaction: discord.Interaction) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not player or not _can_control(interaction, player):
            msg = await language.get_string(interaction.guild_id, "msg_no_permission")
            return await interaction.response.send_message(msg, ephemeral=True)

        await interaction.response.send_message(view=FilterView(), ephemeral=True, delete_after=30)

    async def on_lyrics(self, interaction: discord.Interaction) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not player or not player.current:
            msg = await language.get_string(interaction.guild_id, "msg_no_playing")
            return await interaction.response.send_message(msg, ephemeral=True)

        if not lyrics_service.genius:
            msg = await language.get_string(interaction.guild_id, "msg_lyrics_no_service")
            return await interaction.response.send_message(msg, ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        search_query = _clean_song_title(player.current)
        lyrics_text = await lyrics_service.fetch_lyrics(search_query)

        if not lyrics_text:
            msg = await language.get_string(interaction.guild_id, "msg_lyrics_not_found")
            return await interaction.followup.send(msg, ephemeral=True)

        # Split lyrics into chunks that fit in embeds (max 4096 chars)
        chunks = _split_text(lyrics_text, 4096)
        color = player.bot.embed_color if hasattr(player.bot, 'embed_color') else 0x8000FF

        for i, chunk in enumerate(chunks):
            title = f"📜 {player.current['title']}" if i == 0 else None
            embed = discord.Embed(title=title, description=chunk, color=color)
            if i == len(chunks) - 1:
                embed.set_footer(text="Powered by Genius")
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def on_report(self, interaction: discord.Interaction) -> None:
        await _show_report_modal(interaction)


# ────────────────────────────────────────────────────────────────────────────────
# Text splitting
# ────────────────────────────────────────────────────────────────────────────────

def _split_text(text: str, max_len: int) -> list[str]:
    """Split text into chunks at line boundaries."""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Find last newline before the limit
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


# ────────────────────────────────────────────────────────────────────────────────
# Music Cog
# ────────────────────────────────────────────────────────────────────────────────

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cleanup(self, guild: discord.Guild) -> None:
        await manager.cleanup(guild)

    async def send_np_panel(self, player: MusicPlayer) -> None:
        """Send or update the now-playing panel in the player's channel."""
        guild_id = player.guild.id
        embed = await _build_np_embed(player, guild_id)
        view = await _build_np_view(player, guild_id)

        session = sessions.for_player(player)
        await session.ui.upsert_panel(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        # If the bot itself was disconnected from a channel
        if member.id == self.bot.user.id and before.channel is not None and after.channel is None:
            player = manager.get_existing_player(member.guild.id)
            if player:
                player.stop()
                await manager.cleanup(member.guild)

    @app_commands.guild_only()
    @app_commands.command(name="play", description="Play a song from YouTube, Spotify, or SoundCloud.")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        # LOW-8: Reject excessively long queries to prevent resource abuse
        if len(query) > 200:
            return await interaction.response.send_message(
                "Query too long (max 200 characters).", ephemeral=True,
            )

        if not interaction.user.voice:
            msg = await language.get_string(interaction.guild_id, "msg_error_voice_required")
            return await interaction.response.send_message(msg, ephemeral=True)

        await interaction.response.defer()

        # Connect to voice if not already
        connected_here = False
        if not interaction.guild.voice_client:
            await interaction.user.voice.channel.connect()
            connected_here = True
        elif interaction.guild.voice_client.channel != interaction.user.voice.channel:
            msg = await language.get_string(interaction.guild_id, "msg_error_same_voice_required")
            return await interaction.followup.send(msg, ephemeral=True)

        player = manager.get_player(interaction, cog=self)

        # ── Spotify playlist / album ──────────────────────────────────
        if is_playlist_url(query):
            search_msg = await language.get_string(
                interaction.guild_id, "msg_searching_multi",
            )
            status = await interaction.followup.send(search_msg)

            playlist_tracks = await YTDLSource.extract_playlist(query)
            if not playlist_tracks:
                msg = await language.get_string(interaction.guild_id, "msg_error_no_results")
                await status.edit(content=msg)
                _schedule_delete(status)
                if connected_here:
                    await manager.cleanup(interaction.guild)
                return

            ptype = "playlist" if "playlist/" in query else "album"
            total = len(playlist_tracks)
            added = 0

            # Resolve tracks in batches of 5 for speed
            BATCH = 5
            queue_full = False
            for i in range(0, len(playlist_tracks), BATCH):
                if queue_full:
                    break
                batch = playlist_tracks[i : i + BATCH]
                tasks = [
                    YTDLSource.resolve_playlist_track(t['query']) for t in batch
                ]
                results = await asyncio.gather(*tasks)

                for idx, info in enumerate(results):
                    if not info:
                        continue
                    # Use Spotify thumbnail if yt-dlp didn't find one
                    sp_thumb = batch[idx].get('thumbnail')
                    if sp_thumb and not info.get('thumbnail'):
                        info['thumbnail'] = sp_thumb
                    info["requester_id"] = interaction.user.id
                    if player.enqueue(info):
                        added += 1
                    else:
                        queue_full = True
                        break  # Queue full

            if added == 0:
                msg = await language.get_string(interaction.guild_id, "msg_error_no_results")
                if connected_here:
                    await manager.cleanup(interaction.guild)
            elif added < total:
                msg = await language.get_string(
                    interaction.guild_id, "msg_playlist_partial",
                    added=added, total=total,
                )
            else:
                msg = await language.get_string(
                    interaction.guild_id, "msg_playlist_added",
                    count=added, platform="Spotify", type=ptype,
                )
            await status.edit(content=msg)
            _schedule_delete(status)
            return

        # ── Single track ──────────────────────────────────────────────
        info = await YTDLSource.extract_info(query)

        if not info:
            msg = await language.get_string(interaction.guild_id, "msg_error_no_results")
            sent = await interaction.followup.send(msg)
            _schedule_delete(sent)
            if connected_here:
                await manager.cleanup(interaction.guild)
            return

        # Tag who requested this track
        info["requester_id"] = interaction.user.id

        if not player.enqueue(info):
            msg = await language.get_string(interaction.guild_id, "msg_queue_full", max_size=MAX_QUEUE_SIZE)
            sent = await interaction.followup.send(msg)
            _schedule_delete(sent)
            return

        platform = info.get('platform', 'Unknown')
        found_msg = await language.get_string(
            interaction.guild_id, "msg_found_on", platform=platform,
        )

        if player.current:
            # Song was added to queue (something else is already playing)
            msg = await language.get_string(interaction.guild_id, "msg_queued")
            sent = await interaction.followup.send(
                f"{msg}: **{info['title']}** ({found_msg})",
            )
            _schedule_delete(sent)
        else:
            # Nothing was playing — the panel will be sent by player_loop
            msg = await language.get_string(interaction.guild_id, "msg_playing")
            sent = await interaction.followup.send(
                f"{msg}: **{info['title']}** ({found_msg})",
            )
            _schedule_delete(sent)

    @app_commands.guild_only()
    @app_commands.command(name="skip", description="Skips the current song.")
    async def skip(self, interaction: discord.Interaction) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not await _require_player_control(interaction, player):
            return

        player.skip()
        msg = await language.get_string(interaction.guild_id, "msg_skipped")
        await interaction.response.send_message(msg)
        sent = await interaction.original_response()
        _schedule_delete(sent)

    @app_commands.guild_only()
    @app_commands.command(name="stop", description="Stops the music and clears the queue.")
    async def stop(self, interaction: discord.Interaction) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not await _require_player_control(interaction, player):
            return

        player.stop()
        await manager.cleanup(interaction.guild)

        msg = await language.get_string(interaction.guild_id, "msg_stopped")
        await interaction.response.send_message(msg)
        sent = await interaction.original_response()
        _schedule_delete(sent)

    @app_commands.guild_only()
    @app_commands.command(name="queue", description="Displays the current music queue.")
    async def queue(self, interaction: discord.Interaction) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not player or not player.queue:
            msg = await language.get_string(interaction.guild_id, "msg_queue_empty")
            await interaction.response.send_message(msg)
            sent = await interaction.original_response()
            _schedule_delete(sent)
            return

        embed = await _build_queue_embed(player, interaction.guild_id, self.bot.embed_color)
        await interaction.response.send_message(embed=embed)
        sent = await interaction.original_response()
        _schedule_delete(sent, delay=30)

    @app_commands.guild_only()
    @app_commands.command(name="nowplaying", description="Shows the currently playing song.")
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not player or not player.current:
            msg = await language.get_string(interaction.guild_id, "msg_no_playing")
            return await interaction.response.send_message(msg, ephemeral=True)

        embed = await _build_np_embed(player, interaction.guild_id)
        view = await _build_np_view(player, interaction.guild_id)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.guild_only()
    @app_commands.command(name="filters", description="Apply audio filters (bassboost, nightcore, vaporwave).")
    @app_commands.choices(filter=[
        app_commands.Choice(name="None", value="none"),
        app_commands.Choice(name="Bassboost", value="bassboost"),
        app_commands.Choice(name="Nightcore", value="nightcore"),
        app_commands.Choice(name="Vaporwave", value="vaporwave"),
        app_commands.Choice(name="Karaoke", value="karaoke"),
        app_commands.Choice(name="8D", value="8d"),
    ])
    async def filters(self, interaction: discord.Interaction, filter: app_commands.Choice[str]) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not await _require_player_control(interaction, player):
            return

        player.set_filter(filter.value)
        msg = await language.get_string(
            interaction.guild_id, "msg_filters_applied", filter=filter.name,
        )
        await interaction.response.send_message(msg)
        sent = await interaction.original_response()
        _schedule_delete(sent)

    @app_commands.guild_only()
    @app_commands.command(name="lyrics", description="Show lyrics for the current song or a search query.")
    async def lyrics(self, interaction: discord.Interaction, query: str | None = None) -> None:
        if not lyrics_service.genius:
            msg = await language.get_string(interaction.guild_id, "msg_lyrics_no_service")
            return await interaction.response.send_message(msg, ephemeral=True)

        # Use current track if no query provided
        if not query:
            player = manager.get_existing_player(interaction.guild_id)
            if not player or not player.current:
                msg = await language.get_string(interaction.guild_id, "msg_no_playing")
                return await interaction.response.send_message(msg, ephemeral=True)
            query = _clean_song_title(player.current)

        await interaction.response.defer(ephemeral=True)

        lyrics_text = await lyrics_service.fetch_lyrics(query)

        if not lyrics_text:
            msg = await language.get_string(interaction.guild_id, "msg_lyrics_not_found")
            return await interaction.followup.send(msg, ephemeral=True)

        # Split lyrics into chunks that fit in embeds (max 4096 chars)
        chunks = _split_text(lyrics_text, 4096)

        for i, chunk in enumerate(chunks):
            title = f"📜 {query}" if i == 0 else None
            embed = discord.Embed(title=title, description=chunk, color=self.bot.embed_color)
            if i == len(chunks) - 1:
                embed.set_footer(text="Powered by Genius")
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    bot.add_view(PersistentMusicReportView())
    cog = Music(bot)
    await bot.add_cog(cog)

    music_group = app_commands.Group(name="music", description="Music controls")

    async def track_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        player = manager.get_existing_player(interaction.guild_id)
        choices: list[app_commands.Choice[str]] = []
        if player and player.current:
            title = player.current.get("title", "")
            url = player.current.get("webpage_url", "")
            if title and current.lower() in title.lower():
                choices.append(app_commands.Choice(name=f"Replay: {title}"[:100], value=url or title))
        if current:
            choices.append(app_commands.Choice(name=f"Search: {current}"[:100], value=current[:100]))
        return choices[:25]

    @music_group.command(name="play", description="Play a song from YouTube, Spotify, or SoundCloud.")
    @app_commands.autocomplete(query=track_autocomplete)
    async def music_play(interaction: discord.Interaction, query: str) -> None:
        await cog.play.callback(cog, interaction, query)

    @music_group.command(name="skip", description="Skip the current song.")
    async def music_skip(interaction: discord.Interaction) -> None:
        await cog.skip.callback(cog, interaction)

    @music_group.command(name="stop", description="Stop music and clear the queue.")
    async def music_stop(interaction: discord.Interaction) -> None:
        await cog.stop.callback(cog, interaction)

    @music_group.command(name="nowplaying", description="Show the current song.")
    async def music_nowplaying(interaction: discord.Interaction) -> None:
        await cog.nowplaying.callback(cog, interaction)

    @music_group.command(name="queue", description="View, clear, remove, or move queue items.")
    @app_commands.choices(action=[
        app_commands.Choice(name="View", value="view"),
        app_commands.Choice(name="Clear", value="clear"),
        app_commands.Choice(name="Remove", value="remove"),
        app_commands.Choice(name="Move", value="move"),
    ])
    async def music_queue(
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        index: int | None = None,
        target: int | None = None,
    ) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if action.value == "view":
            await cog.queue.callback(cog, interaction)
            return

        if not await _require_player_control(interaction, player, require_current=False):
            return

        if action.value == "clear":
            player.queue.clear()
            msg = await language.get_string(interaction.guild_id, "msg_queue_cleared")
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if index is None or index < 1 or index > len(player.queue):
            msg = await language.get_string(interaction.guild_id, "msg_queue_invalid_index")
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if action.value == "remove":
            removed = player.queue.remove_at(index - 1)
            msg = await language.get_string(
                interaction.guild_id,
                "msg_queue_removed",
                title=removed.get("title", "Unknown Title"),
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if target is None or target < 1 or target > len(player.queue):
            msg = await language.get_string(interaction.guild_id, "msg_queue_invalid_index")
            await interaction.response.send_message(msg, ephemeral=True)
            return

        player.queue.move(index - 1, target - 1)
        msg = await language.get_string(interaction.guild_id, "msg_queue_moved", index=index, target=target)
        await interaction.response.send_message(msg, ephemeral=True)

    @music_group.command(name="filter", description="Apply an audio filter.")
    @app_commands.choices(filter=[
        app_commands.Choice(name="None", value="none"),
        app_commands.Choice(name="Bassboost", value="bassboost"),
        app_commands.Choice(name="Nightcore", value="nightcore"),
        app_commands.Choice(name="Vaporwave", value="vaporwave"),
        app_commands.Choice(name="Karaoke", value="karaoke"),
        app_commands.Choice(name="8D", value="8d"),
    ])
    async def music_filter(interaction: discord.Interaction, filter: app_commands.Choice[str]) -> None:
        await cog.filters.callback(cog, interaction, filter)

    @music_group.command(name="save", description="Save the current queue.")
    async def music_save(interaction: discord.Interaction, name: str) -> None:
        player = manager.get_existing_player(interaction.guild_id)
        if not await _require_player_control(interaction, player, require_current=False):
            return

        items = [
            item.to_saved_record(position)
            for position, item in enumerate(player.queue.to_saved_items(player.current), start=1)
            if item.webpage_url
        ]
        if not items:
            msg = await language.get_string(interaction.guild_id, "msg_queue_empty")
            await interaction.response.send_message(msg, ephemeral=True)
            return

        await interaction.client.db.save_music_queue(interaction.guild_id, name[:64], interaction.user.id, items)
        msg = await language.get_string(interaction.guild_id, "msg_queue_saved", name=name[:64], count=len(items))
        await interaction.response.send_message(msg, ephemeral=True)

    @music_group.command(name="load", description="Load a saved queue.")
    async def music_load(interaction: discord.Interaction, name: str) -> None:
        if not interaction.user.voice:
            msg = await language.get_string(interaction.guild_id, "msg_error_voice_required")
            await interaction.response.send_message(msg, ephemeral=True)
            return

        rows = await interaction.client.db.load_saved_music_queue(interaction.guild_id, name[:64])
        if not rows:
            msg = await language.get_string(interaction.guild_id, "msg_saved_queue_not_found")
            await interaction.response.send_message(msg, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        if not interaction.guild.voice_client:
            await interaction.user.voice.channel.connect()
        elif interaction.guild.voice_client.channel != interaction.user.voice.channel:
            msg = await language.get_string(interaction.guild_id, "msg_error_same_voice_required")
            await interaction.followup.send(msg, ephemeral=True)
            return

        session = await sessions.for_guild(interaction, cog=cog)
        added = 0
        for row in rows:
            info = await YTDLSource.extract_info(row["webpage_url"])
            if not info:
                info = QueueItem(
                    title=row["title"],
                    webpage_url=row["webpage_url"],
                    stream_url=None,
                    requester_id=interaction.user.id,
                    duration=row["duration"],
                    source=row["source"],
                ).to_track()
            if await session.queue.add(info, requester=interaction.user.id):
                added += 1
            else:
                break

        msg = await language.get_string(interaction.guild_id, "msg_queue_loaded", name=name[:64], count=added)
        await interaction.followup.send(msg, ephemeral=True)

    @music_group.command(name="saved", description="List saved queues.")
    async def music_saved(interaction: discord.Interaction) -> None:
        queues = await interaction.client.db.list_saved_music_queues(interaction.guild_id)
        if not queues:
            msg = await language.get_string(interaction.guild_id, "msg_saved_queues_empty")
            await interaction.response.send_message(msg, ephemeral=True)
            return

        lines = [f"**{q['name']}** — {q['item_count']} tracks" for q in queues[:20]]
        embed = discord.Embed(title="Saved Queues", description="\n".join(lines), color=bot.embed_color)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    bot.tree.add_command(music_group)
