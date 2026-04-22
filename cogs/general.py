import asyncio
import datetime
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from config import OWNER_ID, REPORT_CHANNEL_ID, SUPPORT_SERVER, WEBSITE
from services.database import set_guild_language
from services.language import language

logger = logging.getLogger('MusicBot.General')

_FEEDBACK_DELETE_AFTER = 10


def _schedule_delete(msg: discord.Message, delay: float = _FEEDBACK_DELETE_AFTER) -> None:
    """Schedule a message for deletion after *delay* seconds."""
    async def _do_delete() -> None:
        await asyncio.sleep(delay)
        try:
            await msg.delete()
        except (discord.NotFound, discord.HTTPException):
            pass
    asyncio.create_task(_do_delete())

_REPORT_EMOJI_STR = '<:remove:1111950484534743140>'
_REPORT_UNICODE_FALLBACK = '⚠️'

def _try_report_emoji() -> discord.PartialEmoji | str:
    """Try the custom report emoji; fall back to Unicode if unavailable."""
    try:
        return discord.PartialEmoji.from_str(_REPORT_EMOJI_STR)
    except Exception:
        return _REPORT_UNICODE_FALLBACK


class ReportModal(discord.ui.Modal):
    def __init__(
        self,
        title: str,
        label: str,
        placeholder: str,
        embed_title: str,
        field_user: str,
        field_server: str,
        field_problem: str,
        field_dm: str,
        msg_success: str,
        msg_fail: str,
    ) -> None:
        super().__init__(title=title[:45])
        self.embed_title = embed_title
        self.field_user = field_user
        self.field_server = field_server
        self.field_problem = field_problem
        self.field_dm = field_dm
        self.msg_success = msg_success
        self.msg_fail = msg_fail

        self.problem = discord.ui.TextInput(
            label=label[:45],
            style=discord.TextStyle.paragraph,
            placeholder=placeholder[:100],
            required=True,
            max_length=1500,
        )
        self.add_item(self.problem)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title=self.embed_title,
            color=discord.Color.red(),
            timestamp=interaction.created_at,
        )
        embed.add_field(
            name=self.field_user,
            value=f"{interaction.user} ({interaction.user.id})",
            inline=False,
        )
        guild_info = (
            f"{interaction.guild.name} ({interaction.guild.id})"
            if interaction.guild
            else self.field_dm
        )
        embed.add_field(name=self.field_server, value=guild_info, inline=False)
        embed.add_field(name=self.field_problem, value=self.problem.value, inline=False)

        try:
            target = None

            # Priority 1: dedicated report channel
            if REPORT_CHANNEL_ID:
                target = interaction.client.get_channel(REPORT_CHANNEL_ID)

            # Priority 2: DM the configured owner
            if not target and OWNER_ID:
                target = await interaction.client.fetch_user(OWNER_ID)

            if target:
                await target.send(embed=embed)
                await interaction.response.send_message(self.msg_success, ephemeral=True)
            else:
                await interaction.response.send_message(self.msg_fail, ephemeral=True)
                logger.error("No report target configured (set OWNER_ID or REPORT_CHANNEL_ID in .env)")
        except Exception as e:
            await interaction.response.send_message(self.msg_fail, ephemeral=True)
            logger.error("Failed to send report: %s", e)


async def _show_report_modal(interaction: discord.Interaction) -> None:
    """Build a localized ReportModal and show it — used by both
    the /report command and the persistent report button."""
    guild_id = interaction.guild_id or 0
    keys = [
        "modal_report_title", "modal_report_label", "modal_report_placeholder",
        "emb_report_title", "emb_report_field_user", "emb_report_field_server",
        "emb_report_field_problem", "emb_report_dm",
        "msg_report_success", "msg_report_fail",
    ]

    # Modernization #7: asyncio.gather for concurrent string fetching
    values = await asyncio.gather(*(language.get_string(guild_id, k) for k in keys))
    strings = dict(zip(keys, values))

    await interaction.response.send_modal(ReportModal(
        title=strings["modal_report_title"],
        label=strings["modal_report_label"],
        placeholder=strings["modal_report_placeholder"],
        embed_title=strings["emb_report_title"],
        field_user=strings["emb_report_field_user"],
        field_server=strings["emb_report_field_server"],
        field_problem=strings["emb_report_field_problem"],
        field_dm=strings["emb_report_dm"],
        msg_success=strings["msg_report_success"],
        msg_fail=strings["msg_report_fail"],
    ))


class ReportView(discord.ui.View):
    def __init__(self, btn_label: str = "Report Problem") -> None:
        super().__init__(timeout=None)
        self.report_button_item = discord.ui.Button(
            label=btn_label,
            style=discord.ButtonStyle.danger,
            custom_id="persistent_report_button",
            emoji=_try_report_emoji(),
        )
        self.report_button_item.callback = self.report_button_callback
        self.add_item(self.report_button_item)

    async def report_button_callback(self, interaction: discord.Interaction) -> None:
        await _show_report_modal(interaction)


async def _build_help_embed(guild_id: int | None, bot: commands.Bot) -> discord.Embed:
    guild_id = guild_id or 0
    
    # Calculate dynamic bot stats
    uptime = "Unknown"
    if hasattr(bot, 'start_time'):
        delta = datetime.datetime.now(datetime.UTC) - bot.start_time
        uptime = str(delta).split('.')[0]

    active_voice = len(bot.voice_clients)
    user_count = sum(g.member_count for g in bot.guilds if g.member_count)
    server_count = len(bot.guilds)
    import zoneinfo
    tz = zoneinfo.ZoneInfo(os.getenv("BOT_TIMEZONE", "UTC"))
    now = datetime.datetime.now(tz).strftime("%Y. %m. %d. %H:%M")

    keys = [
        "help_title", "help_desc", "help_cmd_title", "help_cmd_desc",
        "help_btn_title", "help_btn_desc", "help_plat_title", "help_plat_desc",
        "help_feat_title", "help_feat_desc", "help_start_title", "help_start_desc",
    ]
    vals = await asyncio.gather(*(language.get_string(guild_id, k) for k in keys))
    s = dict(zip(keys, vals))

    # Fetches parameterized strings concurrently
    (
        stats_title, stats_desc, links_title, 
        link_web, link_sup, link_inv, footer
    ) = await asyncio.gather(
        language.get_string(guild_id, "help_stats_title"),
        language.get_string(
            guild_id, "help_stats_desc",
            servers=server_count, users=user_count, active=active_voice, uptime=uptime
        ),
        language.get_string(guild_id, "help_links_title"),
        language.get_string(guild_id, "help_link_website", website=WEBSITE),
        language.get_string(guild_id, "help_link_support", support=SUPPORT_SERVER),
        language.get_string(guild_id, "help_link_invite", client_id=bot.user.id),
        language.get_string(guild_id, "help_footer", date=now)
    )

    embed = discord.Embed(
        title=s["help_title"],
        description=s["help_desc"],
        color=bot.embed_color,
    )

    embed.add_field(name=s["help_cmd_title"], value=s["help_cmd_desc"], inline=False)
    embed.add_field(name=s["help_btn_title"], value=s["help_btn_desc"], inline=False)
    embed.add_field(name=s["help_plat_title"], value=s["help_plat_desc"], inline=False)
    embed.add_field(name=s["help_feat_title"], value=s["help_feat_desc"], inline=False)
    embed.add_field(name=s["help_start_title"], value=s["help_start_desc"], inline=False)
    
    embed.add_field(name=stats_title, value=stats_desc, inline=True)
    
    # Conditionally display links
    links_lines = []
    if WEBSITE:
        links_lines.append(link_web)
    if SUPPORT_SERVER:
        links_lines.append(link_sup)
    links_lines.append(link_inv)
    
    embed.add_field(name=links_title, value="\n".join(links_lines), inline=True)
    embed.set_footer(text=footer)

    if bot.user.avatar:
        embed.set_thumbnail(url=bot.user.avatar.url)

    return embed


class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot, report_label: str, refresh_label: str) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.report_button = discord.ui.Button(
            label=report_label,
            style=discord.ButtonStyle.danger,
            custom_id="persistent_help_report_button",
            emoji=_try_report_emoji(),
        )
        self.report_button.callback = self.report_callback
        self.add_item(self.report_button)

        self.refresh_button = discord.ui.Button(
            label=refresh_label,
            style=discord.ButtonStyle.primary,
            custom_id="persistent_help_refresh_button",
            emoji="🔄",
        )
        self.refresh_button.callback = self.refresh_callback
        self.add_item(self.refresh_button)

    async def report_callback(self, interaction: discord.Interaction) -> None:
        await _show_report_modal(interaction)

    async def refresh_callback(self, interaction: discord.Interaction) -> None:
        embed = await _build_help_embed(interaction.guild_id, self.bot)
        await interaction.response.edit_message(embed=embed)


class General(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Replies with bot ping.")
    async def ping(self, interaction: discord.Interaction) -> None:
        lang_str = await language.get_string(
            interaction.guild_id,
            "command_ping_response",
            latency=round(self.bot.latency * 1000),
        )
        await interaction.response.send_message(lang_str)
        sent = await interaction.original_response()
        _schedule_delete(sent)

    @app_commands.command(name="language", description="Set the bot server language.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.choices(lang=[
        app_commands.Choice(name="English", value="en"),
        app_commands.Choice(name="Magyar", value="hu"),
    ])
    async def setlanguage(self, interaction: discord.Interaction, lang: app_commands.Choice[str]) -> None:
        await set_guild_language(interaction.guild_id, lang.value)
        success_msg = await language.get_string(interaction.guild_id, "command_language_success")
        await interaction.response.send_message(success_msg)
        sent = await interaction.original_response()
        _schedule_delete(sent)

    @app_commands.command(name="report", description="Report a problem to the bot developers.")
    async def report(self, interaction: discord.Interaction) -> None:
        await _show_report_modal(interaction)

    @app_commands.command(
        name="setup_report",
        description="Set up a problem reporting panel with a button (Admin only).",
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_report(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id or 0

        # Modernization #7: asyncio.gather for concurrent string fetching
        emb_title, emb_desc, btn_label, msg_succ = await asyncio.gather(
            language.get_string(guild_id, "emb_setup_report_title"),
            language.get_string(guild_id, "emb_setup_report_desc"),
            language.get_string(guild_id, "btn_report_issue"),
            language.get_string(guild_id, "msg_setup_report_success"),
        )

        embed = discord.Embed(
            title=emb_title,
            description=emb_desc,
            color=self.bot.embed_color,
        )

        await interaction.response.send_message(msg_succ, ephemeral=True)
        await interaction.channel.send(embed=embed, view=ReportView(btn_label=btn_label))

    @app_commands.command(name="help", description="Displays the bot's features and commands.")
    async def help(self, interaction: discord.Interaction) -> None:
        """Sends the comprehensive localized help menu."""
        embed = await _build_help_embed(interaction.guild_id, self.bot)
        
        # Fetch button labels
        report_label, refresh_label = await asyncio.gather(
            language.get_string(interaction.guild_id or 0, "btn_report_issue"),
            language.get_string(interaction.guild_id or 0, "btn_refresh")
        )

        view = HelpView(self.bot, report_label, refresh_label)
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(General(bot))
    bot.add_view(ReportView())
    # Add HelpView with dummy labels for persistence (labels are updated per message)
    bot.add_view(HelpView(bot, "Report", "Refresh"))
