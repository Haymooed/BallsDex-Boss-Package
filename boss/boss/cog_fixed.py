# FIXED VERSION OF cog.py (BallsDex v3 compatible)

import discord
import random
import string
import logging

from discord import app_commands
from discord.ext import commands
from typing import TYPE_CHECKING
from discord.ui import Button, View
from datetime import datetime

from settings.models import settings
from bd_models.models import BallInstance, Player, Ball, Special
from ballsdex.core.utils.transformers import BallInstanceTransform, BallTransform, SpecialEnabledTransform

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

from boss.models import (
    BossSettings,
    BossBattle,
    BattleParticipant,
    RoundAction,
    DisqualifiedPlayer
)

log = logging.getLogger("ballsdex.packages.boss")

# ---------------- FIX: PERMISSION SYSTEM ----------------
async def is_owner_or_coowner(interaction: discord.Interaction) -> bool:
    bot = interaction.client
    if not await bot.is_owner(interaction.user) and interaction.user.id not in settings.co_owners:
        raise app_commands.CheckFailure("You do not have permission to use this command.")
    return True
# -------------------------------------------------------


class Boss(commands.GroupCog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    bossadmin = app_commands.Group(name="admin", description="Admin commands for boss battles")

    # ---------------- START ----------------
    @bossadmin.command(name="start")
    @app_commands.check(is_owner_or_coowner)
    async def start(self, interaction: discord.Interaction, countryball: BallTransform, hp_amount: int):
        """Start a boss battle (FIXED PERMISSIONS)"""

        # Check existing battle
        active_battle = await BossBattle.objects.filter(is_active=True).afirst()
        if active_battle:
            return await interaction.response.send_message(
                f"Battle already active with {active_battle.boss_ball.country}",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        # Create battle
        battle = await BossBattle.objects.acreate(
            boss_ball=countryball,
            initial_hp=hp_amount,
            current_hp=hp_amount
        )

        await interaction.followup.send("Boss battle started!", ephemeral=True)

        await interaction.channel.send(
            f"# Boss Battle Started!\n{countryball.country} HP: {hp_amount:,}"
        )

    # ---------------- DEFEND ----------------
    @bossadmin.command(name="defend")
    @app_commands.check(is_owner_or_coowner)
    async def defend(self, interaction: discord.Interaction):
        battle = await BossBattle.objects.filter(is_active=True).afirst()
        if not battle:
            return await interaction.response.send_message("No battle", ephemeral=True)

        battle.is_picking = True
        battle.is_attack_round = False
        battle.current_round += 1
        await battle.asave()

        await interaction.response.send_message("Defend round started", ephemeral=True)

    # ---------------- ATTACK ----------------
    @bossadmin.command(name="attack")
    @app_commands.check(is_owner_or_coowner)
    async def attack(self, interaction: discord.Interaction):
        battle = await BossBattle.objects.filter(is_active=True).afirst()
        if not battle:
            return await interaction.response.send_message("No battle", ephemeral=True)

        battle.is_picking = True
        battle.is_attack_round = True
        battle.current_round += 1
        await battle.asave()

        await interaction.response.send_message("Attack round started", ephemeral=True)

    # ---------------- SELECT ----------------
    @app_commands.command()
    async def select(self, interaction: discord.Interaction, countryball: BallInstanceTransform):
        battle = await BossBattle.objects.filter(is_active=True).afirst()
        if not battle:
            return await interaction.response.send_message("No battle", ephemeral=True)

        participant = await BattleParticipant.objects.filter(
            battle=battle,
            discord_id=interaction.user.id
        ).afirst()

        if not participant:
            return await interaction.response.send_message("Join first", ephemeral=True)

        damage = countryball.attack
        battle.current_hp -= damage
        await battle.asave()

        await interaction.response.send_message(
            f"You dealt {damage:,} damage!",
            ephemeral=True
        )


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Boss(bot))
