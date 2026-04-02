"""
Django management command to run the VATéir Discord bot.

Usage:
    python manage.py runbot

The bot runs as a persistent gateway connection using discord.py,
with full access to the Django ORM for database operations.
"""

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands
from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger("vateir.bot")


class VateirBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.bans = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Sync slash commands
        try:
            from apps.accounts.models import SiteConfig
            config = await asyncio.to_thread(SiteConfig.get)
            if config.discord_guild_id:
                guild = discord.Object(id=int(config.discord_guild_id))
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                logger.info("Synced slash commands to guild %s", config.discord_guild_id)
            else:
                await self.tree.sync()
                logger.info("Synced global slash commands")
        except Exception as exc:
            logger.warning("Failed to sync commands: %s", exc)

    async def on_ready(self):
        logger.info("Bot connected as %s (ID: %s)", self.user, self.user.id)
        logger.info("Connected to %d guild(s)", len(self.guilds))
        # Set status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Irish airspace"
            )
        )

    async def on_member_ban(self, guild, user):
        """Sync bans made directly in Discord to our database."""
        try:
            from apps.notifications.models import DiscordBan, DiscordBotLog
            await asyncio.to_thread(
                _create_discord_ban_record, guild, user
            )
        except Exception as exc:
            logger.error("Failed to sync ban for %s: %s", user, exc)

    async def on_member_unban(self, guild, user):
        """Sync unbans made directly in Discord to our database."""
        try:
            from apps.notifications.models import DiscordBan
            await asyncio.to_thread(
                _handle_discord_unban, guild, user
            )
        except Exception as exc:
            logger.error("Failed to sync unban for %s: %s", user, exc)


def _create_discord_ban_record(guild, user):
    from apps.notifications.models import DiscordBan, DiscordBotLog
    DiscordBan.objects.get_or_create(
        discord_user_id=str(user.id),
        guild_id=str(guild.id),
        is_active=True,
        defaults={
            "discord_username": str(user),
            "reason": "Banned via Discord (synced by bot)",
        },
    )
    DiscordBotLog.objects.create(
        action="ban_sync",
        detail=f"Ban synced from Discord: {user} ({user.id}) in {guild.name}",
    )


def _handle_discord_unban(guild, user):
    from apps.notifications.models import DiscordBan, DiscordBotLog
    from django.utils import timezone
    bans = DiscordBan.objects.filter(
        discord_user_id=str(user.id),
        guild_id=str(guild.id),
        is_active=True,
    )
    for ban in bans:
        ban.is_active = False
        ban.unbanned_at = timezone.now()
        ban.save(update_fields=["is_active", "unbanned_at"])
    DiscordBotLog.objects.create(
        action="unban_sync",
        detail=f"Unban synced from Discord: {user} ({user.id}) in {guild.name}",
    )


# ─── Slash Commands ───────────────────────────────────────────────

bot = VateirBot()


@bot.tree.command(name="status", description="Show bot status")
async def status_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="VATéir Bot Status",
        color=0x059669,
    )
    embed.add_field(name="Latency", value=f"{bot.latency * 1000:.0f}ms", inline=True)
    embed.add_field(name="Guilds", value=str(len(bot.guilds)), inline=True)
    members = sum(g.member_count or 0 for g in bot.guilds)
    embed.add_field(name="Members", value=str(members), inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="announce", description="Post an announcement (staff only)")
@app_commands.describe(title="Announcement title", message="Announcement body", channel="Target channel")
async def announce_command(
    interaction: discord.Interaction,
    title: str,
    message: str,
    channel: discord.TextChannel = None,
):
    # Check if user has admin/staff role in Discord
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("You don't have permission to post announcements.", ephemeral=True)
        return

    target = channel or interaction.channel
    embed = discord.Embed(
        title=title,
        description=message,
        color=0x059669,
    )
    embed.set_author(name="VATéir Control Centre")
    embed.set_footer(text="Announcement")
    await target.send(embed=embed)

    # Log to database
    try:
        from apps.notifications.models import DiscordAnnouncement
        await asyncio.to_thread(
            DiscordAnnouncement.objects.create,
            title=title,
            body=message,
            channel_id=str(target.id),
            channel_name=target.name,
            announcement_type="GENERAL",
        )
    except Exception:
        pass

    await interaction.response.send_message(f"Announcement posted to #{target.name}", ephemeral=True)


@bot.tree.command(name="whois", description="Look up a controller by CID")
@app_commands.describe(cid="VATSIM CID to look up")
async def whois_command(interaction: discord.Interaction, cid: int):
    try:
        from apps.controllers.models import Controller
        controller = await asyncio.to_thread(
            Controller.objects.filter(pk=cid).first
        )
        if not controller:
            await interaction.response.send_message(f"CID {cid} not found in our database.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"{controller.display_name}",
            color=0x059669,
        )
        embed.add_field(name="CID", value=str(controller.cid), inline=True)
        embed.add_field(name="Rating", value=controller.rating_label, inline=True)
        embed.add_field(
            name="Type",
            value="Home" if controller.is_home_controller else "Visitor",
            inline=True,
        )
        await interaction.response.send_message(embed=embed)
    except Exception as exc:
        await interaction.response.send_message(f"Error: {exc}", ephemeral=True)


class Command(BaseCommand):
    help = "Run the VATéir Discord bot"

    def handle(self, *args, **options):
        token = settings.DISCORD_BOT_TOKEN
        if not token:
            self.stderr.write("DISCORD_BOT_TOKEN is not set. Cannot start bot.")
            return

        self.stdout.write("Starting VATéir Discord bot...")
        bot.run(token, log_handler=None)
