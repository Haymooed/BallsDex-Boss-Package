import discord
import logging

from discord import app_commands
from discord.ext import commands
from typing import TYPE_CHECKING, Optional
from discord.ui import Button, View
from django.utils import timezone
import random
import string

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

async def is_owner_or_coowner(interaction: discord.Interaction) -> bool:
    bot = interaction.client
    if not await bot.is_owner(interaction.user) and interaction.user.id not in settings.co_owners:
        raise app_commands.CheckFailure("You do not have permission to use this command.")
    return True


def _random_filename(ext: str) -> str:
    source = string.ascii_uppercase + string.ascii_lowercase + string.ascii_letters
    return f"nt_{''.join(random.choices(source, k=15))}.{ext}"


def _media_file_from_ball(ball: Ball, field_name: str) -> Optional[discord.File]:
    """
    Best-effort helper to load a Ball image from BallsDex's media directory.
    Uses relative path `./admin_panel/media/` which matches BallsDex deploys.
    """
    rel = getattr(ball, field_name, None)
    if not isinstance(rel, str) or not rel:
        return None
    ext = rel.split(".")[-1]
    return discord.File(f"./admin_panel/media/{rel}", filename=_random_filename(ext))


class JoinButton(View):
    def __init__(self, boss_cog: "Boss", battle_id: int):
        super().__init__(timeout=900)
        self.boss_cog = boss_cog
        self.battle_id = battle_id

        join_button = Button(
            label="Join Boss Fight!",
            style=discord.ButtonStyle.primary,
            custom_id=f"boss_join:{battle_id}",
        )
        join_button.callback = self._on_join  # type: ignore[assignment]
        self.add_item(join_button)

    async def _on_join(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        battle = (
            await BossBattle.objects.filter(id=self.battle_id, is_active=True)
            .select_related("boss_ball")
            .afirst()
        )
        if not battle:
            return await interaction.followup.send("No active boss battle.", ephemeral=True)

        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)

        participant, created = await BattleParticipant.objects.aget_or_create(
            battle=battle,
            discord_id=interaction.user.id,
            defaults={"player": player},
        )
        if not created:
            return await interaction.followup.send("You already joined this boss battle.", ephemeral=True)

        await interaction.followup.send("You joined the Boss Battle!", ephemeral=True)


class Boss(commands.GroupCog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    bossadmin = app_commands.Group(name="admin", description="Admin commands for boss battles")

    @bossadmin.command(name="start")
    @app_commands.check(is_owner_or_coowner)
    async def start(
        self,
        interaction: discord.Interaction,
        countryball: BallTransform,
        hp_amount: int,
        start_image: discord.Attachment | None = None,
        defend_image: discord.Attachment | None = None,
        attack_image: discord.Attachment | None = None,
    ):
        """Start a boss battle"""

        active_battle = (
            await BossBattle.objects.filter(is_active=True)
            .select_related("boss_ball")
            .afirst()
        )
        if active_battle:
            return await interaction.response.send_message(
                f"Battle already active with {active_battle.boss_ball.country}",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        battle = await BossBattle.objects.acreate(
            boss_ball=countryball,
            initial_hp=hp_amount,
            current_hp=hp_amount,
            start_image_url=(start_image.url if start_image else None),
            defend_image_url=(defend_image.url if defend_image else None),
            attack_image_url=(attack_image.url if attack_image else None),
        )

        await interaction.followup.send("Boss battle started!", ephemeral=True)

        view = JoinButton(self, battle_id=battle.id)

        file: discord.File | None
        if start_image:
            file = await start_image.to_file()
        else:
            file = _media_file_from_ball(countryball, "collection_card")

        content = f"# Boss Battle Started!\n{countryball.country} HP: {hp_amount:,}"
        if file:
            await interaction.channel.send(content, file=file, view=view)
        else:
            # Fallback without image if the card couldn't be found
            await interaction.channel.send(content, view=view)

    @bossadmin.command(name="defend")
    @app_commands.check(is_owner_or_coowner)
    async def defend(self, interaction: discord.Interaction):
        battle = (
            await BossBattle.objects.filter(is_active=True)
            .select_related("boss_ball")
            .afirst()
        )
        if not battle:
            return await interaction.response.send_message("No battle", ephemeral=True)
        if battle.is_picking:
            return await interaction.response.send_message("There is already an ongoing round", ephemeral=True)
        if battle.current_hp <= 0:
            return await interaction.response.send_message("The Boss is dead", ephemeral=True)

        battle.is_picking = True
        battle.is_attack_round = False
        battle.current_round += 1
        await battle.asave()

        await interaction.response.send_message("Defend round started", ephemeral=True)

        embed = None
        file = None
        if battle.defend_image_url:
            embed = discord.Embed(
                description=f"Round {battle.current_round}\n# {battle.boss_ball.country} is preparing to defend!"
            )
            embed.set_image(url=battle.defend_image_url)
        else:
            file = _media_file_from_ball(battle.boss_ball, "wild_card")

        header = f"Round {battle.current_round}\n# {battle.boss_ball.country} is preparing to defend!"
        if embed:
            await interaction.channel.send(embed=embed)
        else:
            await interaction.channel.send(header, file=file) if file else await interaction.channel.send(header)
        await interaction.channel.send(
            f"> Use `/boss select` to select your attacking {settings.collectible_name}.\n"
            f"> Your selected {settings.collectible_name}'s ATK will be used to attack."
        )

    @bossadmin.command(name="attack")
    @app_commands.check(is_owner_or_coowner)
    async def attack(self, interaction: discord.Interaction, attack_amount: int | None = None):
        battle = (
            await BossBattle.objects.filter(is_active=True)
            .select_related("boss_ball")
            .afirst()
        )
        if not battle:
            return await interaction.response.send_message("No battle", ephemeral=True)
        if battle.is_picking:
            return await interaction.response.send_message("There is already an ongoing round", ephemeral=True)
        if battle.current_hp <= 0:
            return await interaction.response.send_message("The Boss is dead", ephemeral=True)

        battle.is_picking = True
        battle.is_attack_round = True
        battle.current_round += 1
        boss_settings = await BossSettings.load()
        battle.boss_attack_amount = (
            attack_amount
            if attack_amount is not None
            else random.randrange(boss_settings.min_boss_damage, boss_settings.max_boss_damage + 1, 100)
        )
        await battle.asave()

        await interaction.response.send_message("Attack round started", ephemeral=True)

        embed = None
        file = None
        if battle.attack_image_url:
            embed = discord.Embed(
                description=f"Round {battle.current_round}\n# {battle.boss_ball.country} is preparing to attack!"
            )
            embed.set_image(url=battle.attack_image_url)
        else:
            file = _media_file_from_ball(battle.boss_ball, "wild_card")

        header = f"Round {battle.current_round}\n# {battle.boss_ball.country} is preparing to attack!"
        if embed:
            await interaction.channel.send(embed=embed)
        else:
            await interaction.channel.send(header, file=file) if file else await interaction.channel.send(header)
        await interaction.channel.send(
            f"> Use `/boss select` to select your defending {settings.collectible_name}.\n"
            f"> Your selected {settings.collectible_name}'s HP will be used to defend."
        )

    @app_commands.command(name="join")
    async def join(self, interaction: discord.Interaction):
        battle = (
            await BossBattle.objects.filter(is_active=True)
            .select_related("boss_ball")
            .afirst()
        )
        if not battle:
            return await interaction.response.send_message("No active boss battle.", ephemeral=True)

        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        _, created = await BattleParticipant.objects.aget_or_create(
            battle=battle,
            discord_id=interaction.user.id,
            defaults={"player": player},
        )
        if not created:
            return await interaction.response.send_message("You already joined this boss battle.", ephemeral=True)

        return await interaction.response.send_message("You joined the Boss Battle!", ephemeral=True)

    @app_commands.command()
    async def select(self, interaction: discord.Interaction, countryball: BallInstanceTransform):
        battle = (
            await BossBattle.objects.filter(is_active=True)
            .select_related("boss_ball")
            .afirst()
        )
        if not battle:
            return await interaction.response.send_message("No battle", ephemeral=True)
        if not battle.is_picking:
            return await interaction.response.send_message("It is not yet time to select.", ephemeral=True)

        participant = await BattleParticipant.objects.filter(
            battle=battle,
            discord_id=interaction.user.id
        ).afirst()

        if not participant:
            return await interaction.response.send_message("Join first", ephemeral=True)
        if not participant.is_alive:
            return await interaction.response.send_message("You are dead/disqualified.", ephemeral=True)

        if battle.is_attack_round:
            # Boss attacks: players defend using HP.
            defended_hp = max(int(getattr(countryball, "health", 0)), 0)
            participant.total_damage_taken += int(battle.boss_attack_amount)
            if battle.boss_attack_amount >= defended_hp:
                participant.is_alive = False
                participant.died_at = timezone.now()
                await participant.asave()
                return await interaction.response.send_message(
                    f"You defended with {defended_hp:,} HP and died.",
                    ephemeral=True,
                )
            await participant.asave()
            return await interaction.response.send_message(
                f"You defended with {defended_hp:,} HP and survived.",
                ephemeral=True,
            )

        # Players attack: use ATK to damage boss.
        damage = max(int(getattr(countryball, "attack", 0)), 0)
        battle.current_hp -= damage
        participant.total_damage_dealt += damage
        battle.last_hitter_id = interaction.user.id

        await battle.asave()
        await participant.asave()

        await interaction.response.send_message(
            f"You dealt {damage:,} damage!",
            ephemeral=True
        )


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Boss(bot))
