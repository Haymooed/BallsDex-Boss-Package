import discord
import logging

from discord import app_commands
from discord.ext import commands
from typing import TYPE_CHECKING, Optional
from discord.ui import Button, View
from django.utils import timezone
from django.core.files.storage import default_storage
import os
import random
import string

from settings.models import settings
from bd_models.models import BallInstance, Player, Ball, Special, balls as balls_cache
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


class BossBallTransform(app_commands.Transformer):
    """
    A stable Ball transformer for /boss admin start.

    We intentionally avoid relying on BallsDex's built-in transformers here because
    an exception in their autocomplete will surface as Discord's "Loading options failed".
    """

    async def transform(self, interaction: discord.Interaction, value: str) -> Ball:
        q = (value or "").strip()
        if not q:
            raise app_commands.TransformError(value, self)

        lowered = q.casefold()
        for ball in balls_cache.values():
            if ball.country.casefold() == lowered:
                return ball

        found = await Ball.objects.filter(country__iexact=q).afirst()
        if not found:
            raise app_commands.TransformError(value, self)
        return found

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        cur = (current or "").strip().casefold()
        results: list[app_commands.Choice[str]] = []

        # Prefer cache to avoid DB calls in autocomplete
        for ball in balls_cache.values():
            name = ball.country
            if not cur or cur in name.casefold():
                results.append(app_commands.Choice(name=name, value=name))
            if len(results) >= 25:
                break
        return results


def _random_filename(ext: str) -> str:
    source = string.ascii_uppercase + string.ascii_lowercase + string.ascii_letters
    return f"nt_{''.join(random.choices(source, k=15))}.{ext}"


def _media_file_from_ball(ball: Ball, field_name: str) -> Optional[discord.File]:
    """
    Best-effort helper to load a Ball image from storage.

    Supports both:
    - Image/FileField objects (Ball.collection_card / Ball.wild_card in BD3)
    - Plain string paths (legacy style, relative to ./admin_panel/media/)
    """
    img_field = getattr(ball, field_name, None)
    if not img_field:
        return None

    # Modern BD3: ImageFieldFile with .path / .name
    try:
        file_path = getattr(img_field, "path", None)
        if file_path and os.path.exists(file_path):
            ext = os.path.basename(file_path).split(".")[-1]
            return discord.File(file_path, filename=_random_filename(ext))
    except Exception:
        pass

    rel = getattr(img_field, "name", img_field)
    if isinstance(rel, str) and rel:
        try:
            storage_path = default_storage.path(rel)
            if os.path.exists(storage_path):
                ext = os.path.basename(storage_path).split(".")[-1]
                return discord.File(storage_path, filename=_random_filename(ext))
        except Exception:
            pass

        fallback = f"./admin_panel/media/{rel}"
        if os.path.exists(fallback):
            ext = os.path.basename(fallback).split(".")[-1]
            return discord.File(fallback, filename=_random_filename(ext))

    return None


def _file_from_url_or_path(value: str) -> Optional[discord.File]:
    """
    Supports both:
    - Absolute URLs (we will embed these)
    - Stored media paths like `balls/foo.png` (we will upload as a file if present on disk)
    """
    raw = (value or "").strip()
    if not raw or raw.startswith(("http://", "https://")):
        return None

    try:
        path = default_storage.path(raw)
        if os.path.exists(path):
            ext = os.path.basename(path).split(".")[-1]
            return discord.File(path, filename=_random_filename(ext))
    except Exception:
        pass

    fallback = f"./admin_panel/media/{raw}"
    if os.path.exists(fallback):
        ext = os.path.basename(fallback).split(".")[-1]
        return discord.File(fallback, filename=_random_filename(ext))

    return None


def _build_image_payload(*, title: str, image_value: Optional[str], fallback_file: Optional[discord.File]):
    """
    Returns either an embed (for http URLs) or a file upload (for local paths).
    """
    if image_value:
        v = image_value.strip()
        if v.startswith(("http://", "https://")):
            embed = discord.Embed(description=title)
            embed.set_image(url=v)
            return {"embed": embed, "file": None}

        file = _file_from_url_or_path(v)
        if file:
            return {"embed": None, "file": file}

    return {"embed": None, "file": fallback_file}


def _rarity_multiplier(ball_rarity: float, weather: str) -> float:
    """
    Apply a simple rarity-based modifier depending on current weather.
    `ball_rarity` is a BallsDex rarity (float, lower is rarer in many setups).
    We don't assume a specific scale; we bucket by rough ranges.
    """
    r = float(ball_rarity)

    is_common = r >= 100.0
    is_rare = 50.0 <= r < 100.0
    is_ultra = r < 25.5

    if weather == "STORM":
        return 0.85 if is_common else 1.0
    if weather == "BLESS":
        return 1.15 if (is_rare or is_ultra) else 1.0
    if weather == "FOG":
        return 0.90 if is_ultra else 1.0
    return 1.0


def _weather_label(weather: str) -> str:
    return {
        "CLEAR": "Clear",
        "STORM": "Storm",
        "BLESS": "Blessing",
        "FOG": "Fog",
    }.get(weather, weather)


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
        join_button.callback = self._on_join
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
    round = app_commands.Group(name="round", description="Round management commands")

    @bossadmin.command(name="start", description="Start a new boss battle")
    @app_commands.check(is_owner_or_coowner)
    @app_commands.describe(
        countryball="The ball to use as the boss",
        hp_amount="Boss HP to start with",
        weather="Weather condition (rarity-based effects)",
        start_image="Optional image shown when the battle starts",
        defend_image="Optional image shown during defend rounds",
        attack_image="Optional image shown during attack rounds",
    )
    @app_commands.choices(
        weather=[
            app_commands.Choice(name="Clear (no effects)", value="CLEAR"),
            app_commands.Choice(name="Storm (common balls weaker)", value="STORM"),
            app_commands.Choice(name="Blessing (rare balls stronger)", value="BLESS"),
            app_commands.Choice(name="Fog (ultra-rare balls weaker)", value="FOG"),
        ]
    )
    async def start(
        self,
        interaction: discord.Interaction,
        countryball: app_commands.Transform[Ball, BossBallTransform],
        hp_amount: int,
        weather: str = "CLEAR",
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
            weather=weather,
        )

        await interaction.followup.send("Boss battle started!", ephemeral=True)

        view = JoinButton(self, battle_id=battle.id)

        file: discord.File | None
        if start_image:
            file = await start_image.to_file()
        else:
            file = _media_file_from_ball(countryball, "collection_card")

        content = (
            f"# Boss Battle Started!\n"
            f"{countryball.country} HP: {hp_amount:,}\n"
            f"-# Weather: **{_weather_label(weather)}**"
        )
        if file:
            await interaction.channel.send(content, file=file, view=view)
        else:
            await interaction.channel.send(content, view=view)

    @bossadmin.command(name="defend", description="Start a defend round (players attack the boss)")
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

        header = f"Round {battle.current_round}\n# {battle.boss_ball.country} is preparing to defend!"
        fallback_file = _media_file_from_ball(battle.boss_ball, "wild_card")
        payload = _build_image_payload(
            title=header,
            image_value=battle.defend_image_url,
            fallback_file=fallback_file,
        )

        if payload["embed"]:
            await interaction.channel.send(embed=payload["embed"])
        elif payload["file"]:
            await interaction.channel.send(header, file=payload["file"])
        else:
            await interaction.channel.send(header)
        await interaction.channel.send(
            f"> Use `/boss select` to select your attacking {settings.collectible_name}.\n"
            f"> Your selected {settings.collectible_name}'s ATK will be used to attack."
        )

    @bossadmin.command(name="attack", description="Start an attack round (boss attacks players)")
    @app_commands.check(is_owner_or_coowner)
    @app_commands.describe(attack_amount="Optional boss damage (leave empty for RNG)")
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

        header = f"Round {battle.current_round}\n# {battle.boss_ball.country} is preparing to attack!"
        fallback_file = _media_file_from_ball(battle.boss_ball, "wild_card")
        payload = _build_image_payload(
            title=header,
            image_value=battle.attack_image_url,
            fallback_file=fallback_file,
        )

        if payload["embed"]:
            await interaction.channel.send(embed=payload["embed"])
        elif payload["file"]:
            await interaction.channel.send(header, file=payload["file"])
        else:
            await interaction.channel.send(header)
        await interaction.channel.send(
            f"> Use `/boss select` to select your defending {settings.collectible_name}.\n"
            f"> Your selected {settings.collectible_name}'s HP will be used to defend."
        )

    @round.command(name="end", description="End the current round and show results")
    @app_commands.check(is_owner_or_coowner)
    async def round_end(self, interaction: discord.Interaction):
        battle = (
            await BossBattle.objects.filter(is_active=True)
            .select_related("boss_ball")
            .afirst()
        )
        if not battle:
            return await interaction.response.send_message("No battle", ephemeral=True)
        if not battle.is_picking:
            return await interaction.response.send_message("There is no ongoing round.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)
        battle.is_picking = False
        await battle.asave()

        actions = [
            a
            async for a in RoundAction.objects.filter(battle=battle, round_number=battle.current_round)
            .select_related("participant")
            .order_by("-created_at")[:200]
        ]

        damage_by_user: dict[int, int] = {}
        deaths: list[int] = []
        for a in actions:
            uid = int(a.participant.discord_id)
            if battle.is_attack_round:
                pass
            else:
                damage_by_user[uid] = damage_by_user.get(uid, 0) + int(a.damage_dealt)

        if battle.is_attack_round:
            async for p in BattleParticipant.objects.filter(battle=battle, is_alive=False):
                deaths.append(int(p.discord_id))

        embed = discord.Embed(
            title=f"Round {battle.current_round} ended",
            description=(
                f"Boss: **{battle.boss_ball.country}**\n"
                f"Boss HP: **{max(battle.current_hp, 0):,} / {battle.initial_hp:,}**\n"
                f"Weather: **{_weather_label(battle.weather)}**"
            ),
            colour=discord.Colour.blurple(),
        )

        if not battle.is_attack_round:
            if damage_by_user:
                top = sorted(damage_by_user.items(), key=lambda kv: kv[1], reverse=True)[:10]
                lines = [f"{i+1}. <@{uid}> — **{dmg:,}** dmg" for i, (uid, dmg) in enumerate(top)]
                embed.add_field(name="Top damage", value="\n".join(lines)[:1024], inline=False)
            else:
                embed.add_field(name="Top damage", value="No selections this round.", inline=False)
        else:
            embed.add_field(
                name="Boss attack",
                value=f"Boss dealt **{battle.boss_attack_amount:,}** damage to each defender (weather affects defenses).",
                inline=False,
            )
            if deaths:
                embed.add_field(
                    name="Fallen players",
                    value=(", ".join(f"<@{uid}>" for uid in deaths))[:1024],
                    inline=False,
                )

        await interaction.followup.send("Round ended.", ephemeral=True)
        await interaction.channel.send(embed=embed)

    @app_commands.command(name="join", description="Join the active boss battle")
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

    @bossadmin.command(name="hackjoin", description="Manually add a user to the boss battle")
    @app_commands.check(is_owner_or_coowner)
    @app_commands.describe(user="User to add (optional)", user_id="User ID to add (optional)")
    async def hackjoin(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
        user_id: str | None = None,
    ):
        battle = (
            await BossBattle.objects.filter(is_active=True)
            .select_related("boss_ball")
            .afirst()
        )
        if not battle:
            return await interaction.response.send_message("No active boss battle.", ephemeral=True)

        if (user and user_id) or (not user and not user_id):
            return await interaction.response.send_message(
                "Provide either `user` or `user_id` (not both).",
                ephemeral=True,
            )

        target_id: int
        if user:
            target_id = int(user.id)
        else:
            try:
                target_id = int(str(user_id))
            except ValueError:
                return await interaction.response.send_message("Invalid user_id.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        player, _ = await Player.objects.aget_or_create(discord_id=target_id)
        _, created = await BattleParticipant.objects.aget_or_create(
            battle=battle,
            discord_id=target_id,
            defaults={"player": player},
        )

        await interaction.followup.send(
            "User added to the boss battle." if created else "User is already in the boss battle.",
            ephemeral=True,
        )

    @bossadmin.command(name="end", description="Force end the boss battle")
    @app_commands.check(is_owner_or_coowner)
    async def end(self, interaction: discord.Interaction):
        battle = (
            await BossBattle.objects.filter(is_active=True)
            .select_related("boss_ball")
            .afirst()
        )
        if not battle:
            return await interaction.response.send_message("No active boss battle.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        battle.is_active = False
        battle.is_picking = False
        battle.ended_at = timezone.now()
        await battle.asave()

        await interaction.followup.send("Boss battle ended.", ephemeral=True)
        await interaction.channel.send(
            embed=discord.Embed(
                title="Boss battle ended",
                description=(
                    f"Boss: **{battle.boss_ball.country}**\n"
                    f"Final HP: **{max(battle.current_hp, 0):,} / {battle.initial_hp:,}**\n"
                    f"Rounds: **{battle.current_round}**"
                ),
                colour=discord.Colour.red(),
            )
        )

    @app_commands.command(name="select", description="Select a ball for the current round")
    @app_commands.describe(countryball="The ball instance you want to use this round")
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
            mult = _rarity_multiplier(float(getattr(countryball.ball, "rarity", 1.0)), battle.weather)  # type: ignore[attr-defined]
            defended_hp = int(defended_hp * mult)
            participant.total_damage_taken += int(battle.boss_attack_amount)
            if battle.boss_attack_amount >= defended_hp:
                participant.is_alive = False
                participant.died_at = timezone.now()
                await participant.asave()
                await RoundAction.objects.acreate(
                    battle=battle,
                    participant=participant,
                    round_number=battle.current_round,
                    ball_used_id=countryball.id,
                    damage_dealt=0,
                    damage_taken=int(battle.boss_attack_amount),
                )
                return await interaction.response.send_message(
                    f"You defended with {defended_hp:,} HP (weather applied) and died.",
                    ephemeral=True,
                )
            await participant.asave()
            await RoundAction.objects.acreate(
                battle=battle,
                participant=participant,
                round_number=battle.current_round,
                ball_used_id=countryball.id,
                damage_dealt=0,
                damage_taken=int(battle.boss_attack_amount),
            )
            return await interaction.response.send_message(
                f"You defended with {defended_hp:,} HP (weather applied) and survived.",
                ephemeral=True,
            )

        # Players attack: use ATK to damage boss.
        base_damage = max(int(getattr(countryball, "attack", 0)), 0)
        mult = _rarity_multiplier(float(getattr(countryball.ball, "rarity", 1.0)), battle.weather)  # type: ignore[attr-defined]
        damage = int(base_damage * mult)
        battle.current_hp -= damage
        participant.total_damage_dealt += damage
        battle.last_hitter_id = interaction.user.id

        await battle.asave()
        await participant.asave()
        await RoundAction.objects.acreate(
            battle=battle,
            participant=participant,
            round_number=battle.current_round,
            ball_used_id=countryball.id,
            damage_dealt=damage,
            damage_taken=0,
        )

        await interaction.response.send_message(
            f"You dealt {damage:,} damage! (weather applied)",
            ephemeral=True
        )


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Boss(bot))
