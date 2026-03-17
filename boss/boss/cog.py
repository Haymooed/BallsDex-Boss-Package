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


async def log_action(message: str, bot: "BallsDexBot", settings_override: int | None = None):
    channel_id = settings_override or (await BossSettings.load()).log_channel_id
    if not channel_id:
        return
    
    channel = bot.get_channel(channel_id)
    if not channel:
        log.warning(f"Log channel {channel_id} not found")
        return
    if not isinstance(channel, discord.TextChannel):
        log.warning(f"Channel {channel.name} is not a text channel")
        return
    
    try:
        await channel.send(message)
    except Exception as e:
        log.error(f"Failed to send log message: {e}")


class JoinButton(View):
    def __init__(self, boss_cog, battle: BossBattle):
        super().__init__(timeout=None)
        self.boss_cog = boss_cog
        self.battle = battle
        self.join_button = Button(
            label="Join Boss Fight!",
            style=discord.ButtonStyle.primary,
            custom_id=f"join_boss_{battle.id}"
        )
        self.join_button.callback = self.button_callback
        self.add_item(self.join_button)

    async def button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        battle = await BossBattle.objects.filter(id=self.battle.id, is_active=True).afirst()
        if not battle:
            return await interaction.followup.send("This boss battle is no longer active.", ephemeral=True)
        
        disqualified = await DisqualifiedPlayer.objects.filter(
            battle=battle,
            discord_id=interaction.user.id
        ).aexists()
        
        if disqualified:
            return await interaction.followup.send("You have been disqualified from this battle.", ephemeral=True)
        
        participant_exists = await BattleParticipant.objects.filter(
            battle=battle,
            discord_id=interaction.user.id
        ).aexists()
        
        if participant_exists:
            return await interaction.followup.send("You have already joined this boss battle!", ephemeral=True)
        
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        await BattleParticipant.objects.acreate(
            battle=battle,
            player=player,
            discord_id=interaction.user.id
        )
        
        await interaction.followup.send("You have joined the Boss Battle!", ephemeral=True)
        
        await log_action(
            f"{interaction.user} has joined the {battle.boss_ball.country} Boss Battle.",
            self.boss_cog.bot,
            (await BossSettings.load()).log_channel_id
        )


class Boss(commands.GroupCog):
    """
    Boss Battle commands - Fight epic bosses for rare rewards!
    
    Original package by MoOfficial (@moofficial on Discord)
    BallsDex 3.0 conversion by haymooed
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    bossadmin = app_commands.Group(name="admin", description="Admin commands for boss battles")

    @bossadmin.command(name="start")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def start(
        self,
        interaction: discord.Interaction,
        countryball: BallTransform,
        hp_amount: int,
        start_image: discord.Attachment | None = None,
        defend_image: discord.Attachment | None = None,
        attack_image: discord.Attachment | None = None
    ):
        """
        Start a new boss battle
        
        Parameters
        ----------
        countryball: Ball
            The countryball to use as the boss
        hp_amount: int
            Starting HP for the boss
        start_image: discord.Attachment
            Custom image for battle start (optional)
        defend_image: discord.Attachment
            Custom image for defend rounds (optional)
        attack_image: discord.Attachment
            Custom image for attack rounds (optional)
        """
        active_battle = await BossBattle.objects.filter(is_active=True).afirst()
        if active_battle:
            return await interaction.response.send_message(
                f"There is already an active boss battle with {active_battle.boss_ball.country}!",
                ephemeral=True
            )
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        battle = await BossBattle.objects.acreate(
            boss_ball=countryball,
            initial_hp=hp_amount,
            current_hp=hp_amount,
            start_image_url=start_image.url if start_image else None,
            defend_image_url=defend_image.url if defend_image else None,
            attack_image_url=attack_image.url if attack_image else None
        )
        
        def generate_random_name():
            source = string.ascii_uppercase + string.ascii_lowercase
            return "".join(random.choices(source, k=15))
        
        if start_image:
            file = await start_image.to_file()
        else:
            extension = countryball.collection_card.split(".")[-1]
            file_location = "./admin_panel/media/" + countryball.collection_card
            file_name = f"boss_{generate_random_name()}.{extension}"
            file = discord.File(file_location, filename=file_name)
        
        view = JoinButton(self, battle)
        
        await interaction.followup.send("Boss battle successfully started!", ephemeral=True)
        
        message = await interaction.channel.send(
            f"# The boss battle has begun! {self.bot.get_emoji(countryball.emoji_id)}\n"
            f"-# HP: {hp_amount:,}",
            file=file,
            view=view
        )
        
        view.message = message
        
        await log_action(
            f"**BOSS STARTED**: {countryball.country} with {hp_amount:,} HP by {interaction.user}",
            self.bot,
            (await BossSettings.load()).log_channel_id
        )

    @bossadmin.command(name="defend")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def defend(self, interaction: discord.Interaction):
        """
        Start a defend round where players attack the boss
        """
        battle = await BossBattle.objects.filter(is_active=True).afirst()
        if not battle:
            return await interaction.response.send_message("No active boss battle.", ephemeral=True)
        
        if battle.is_picking:
            return await interaction.response.send_message(
                "A round is already in progress!",
                ephemeral=True
            )
        
        participant_count = await BattleParticipant.objects.filter(
            battle=battle,
            is_alive=True
        ).acount()
        
        if participant_count == 0:
            return await interaction.response.send_message(
                "No alive players to start a round!",
                ephemeral=True
            )
        
        if battle.current_hp <= 0:
            return await interaction.response.send_message(
                "The boss is already defeated!",
                ephemeral=True
            )
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        battle.current_round += 1
        battle.is_picking = True
        battle.is_attack_round = False
        await battle.asave()
        
        def generate_random_name():
            source = string.ascii_uppercase + string.ascii_lowercase
            return "".join(random.choices(source, k=15))
        
        if battle.defend_image_url:
            file = await discord.Attachment.from_url(battle.defend_image_url).to_file()
        else:
            extension = battle.boss_ball.wild_card.split(".")[-1]
            file_location = "./admin_panel/media/" + battle.boss_ball.wild_card
            file_name = f"defend_{generate_random_name()}.{extension}"
            file = discord.File(file_location, filename=file_name)
        
        await interaction.followup.send("Defend round started!", ephemeral=True)
        
        await interaction.channel.send(
            f"**Round {battle.current_round}**\n"
            f"# {battle.boss_ball.country} is defending! {self.bot.get_emoji(battle.boss_ball.emoji_id)}",
            file=file
        )
        
        await interaction.channel.send(
            f"> Use `/boss select` to choose your attacking {settings.collectible_name}.\n"
            f"> Your {settings.collectible_name}'s **ATK** will damage the boss!"
        )

    @bossadmin.command(name="attack")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def attack(self, interaction: discord.Interaction, attack_amount: int | None = None):
        """
        Start an attack round where the boss attacks players
        
        Parameters
        ----------
        attack_amount: int
            Boss attack damage (optional, uses random if not specified)
        """
        battle = await BossBattle.objects.filter(is_active=True).afirst()
        if not battle:
            return await interaction.response.send_message("No active boss battle.", ephemeral=True)
        
        if battle.is_picking:
            return await interaction.response.send_message(
                "A round is already in progress!",
                ephemeral=True
            )
        
        participant_count = await BattleParticipant.objects.filter(
            battle=battle,
            is_alive=True
        ).acount()
        
        if participant_count == 0:
            return await interaction.response.send_message(
                "No alive players to start a round!",
                ephemeral=True
            )
        
        if battle.current_hp <= 0:
            return await interaction.response.send_message(
                "The boss is already defeated!",
                ephemeral=True
            )
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        boss_settings = await BossSettings.load()
        
        if attack_amount is None:
            attack_amount = random.randint(boss_settings.min_boss_damage, boss_settings.max_boss_damage)
        
        battle.current_round += 1
        battle.is_picking = True
        battle.is_attack_round = True
        battle.boss_attack_amount = attack_amount
        await battle.asave()
        
        def generate_random_name():
            source = string.ascii_uppercase + string.ascii_lowercase
            return "".join(random.choices(source, k=15))
        
        if battle.attack_image_url:
            file = await discord.Attachment.from_url(battle.attack_image_url).to_file()
        else:
            extension = battle.boss_ball.wild_card.split(".")[-1]
            file_location = "./admin_panel/media/" + battle.boss_ball.wild_card
            file_name = f"attack_{generate_random_name()}.{extension}"
            file = discord.File(file_location, filename=file_name)
        
        await interaction.followup.send(f"Attack round started! Boss will deal {attack_amount:,} damage.", ephemeral=True)
        
        await interaction.channel.send(
            f"**Round {battle.current_round}**\n"
            f"# {battle.boss_ball.country} is attacking! {self.bot.get_emoji(battle.boss_ball.emoji_id)}",
            file=file
        )
        
        await interaction.channel.send(
            f"> Use `/boss select` to choose your defending {settings.collectible_name}.\n"
            f"> Your {settings.collectible_name}'s **HP** will protect you from **{attack_amount:,}** damage!"
        )

    @bossadmin.command(name="end_round")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def end_round(self, interaction: discord.Interaction):
        """
        End the current round and display results
        """
        battle = await BossBattle.objects.filter(is_active=True).afirst()
        if not battle:
            return await interaction.response.send_message("No active boss battle.", ephemeral=True)
        
        if not battle.is_picking:
            return await interaction.response.send_message(
                "No round in progress! Use `/boss admin defend` or `/boss admin attack` to start one.",
                ephemeral=True
            )
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        battle.is_picking = False
        await battle.asave()
        
        actions = [action async for action in RoundAction.objects.filter(
            battle=battle,
            round_number=battle.current_round
        ).select_related("participant")]
        
        result_text = ""
        
        if battle.is_attack_round:
            participants = [p async for p in BattleParticipant.objects.filter(battle=battle, is_alive=True)]
            
            for participant in participants:
                action = next((a for a in actions if a.participant.discord_id == participant.discord_id), None)
                
                if not action:
                    participant.is_alive = False
                    participant.died_at = datetime.now()
                    await participant.asave()
                    
                    user = await self.bot.fetch_user(participant.discord_id)
                    result_text += f"{user} did not select in time and died!\n"
            
            alive_count = await BattleParticipant.objects.filter(battle=battle, is_alive=True).acount()
            
            if alive_count == 0:
                await interaction.followup.send("Round ended - all players eliminated!", ephemeral=True)
                await interaction.channel.send(
                    f"# Round {battle.current_round} has ended {self.bot.get_emoji(battle.boss_ball.emoji_id)}\n"
                    f"The boss dealt **{battle.boss_attack_amount:,}** damage and defeated all players!"
                )
            else:
                await interaction.followup.send("Round ended!", ephemeral=True)
                await interaction.channel.send(
                    f"# Round {battle.current_round} has ended {self.bot.get_emoji(battle.boss_ball.emoji_id)}\n"
                    f"The boss dealt **{battle.boss_attack_amount:,}** damage!"
                )
        else:
            await interaction.followup.send("Round ended!", ephemeral=True)
            
            if battle.current_hp <= 0:
                await interaction.channel.send(
                    f"# Round {battle.current_round} has ended {self.bot.get_emoji(battle.boss_ball.emoji_id)}\n"
                    f"The boss has been **DEFEATED**! HP remaining: **0**"
                )
            else:
                await interaction.channel.send(
                    f"# Round {battle.current_round} has ended {self.bot.get_emoji(battle.boss_ball.emoji_id)}\n"
                    f"Boss HP remaining: **{battle.current_hp:,}** / **{battle.initial_hp:,}**"
                )
        
        if result_text and len(result_text) < 1900:
            await interaction.channel.send(result_text)

    @bossadmin.command(name="conclude")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    @app_commands.choices(
        winner=[
            app_commands.Choice(name="Random", value="RNG"),
            app_commands.Choice(name="Most Damage", value="DMG"),
            app_commands.Choice(name="Last Hitter", value="LAST"),
            app_commands.Choice(name="No Winner", value="NONE"),
        ]
    )
    async def conclude(self, interaction: discord.Interaction, winner: str):
        """
        Conclude the boss battle and award winner
        
        Parameters
        ----------
        winner: str
            How to determine the winner
        """
        battle = await BossBattle.objects.filter(is_active=True).afirst()
        if not battle:
            return await interaction.response.send_message("No active boss battle.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        battle.is_active = False
        battle.is_picking = False
        battle.winner_type = winner
        battle.ended_at = datetime.now()
        
        alive_participants = [p async for p in BattleParticipant.objects.filter(
            battle=battle,
            is_alive=True
        ).order_by("-total_damage_dealt")]
        
        winner_participant = None
        
        if winner == "DMG" and alive_participants:
            winner_participant = alive_participants[0]
        elif winner == "LAST":
            if battle.last_hitter_id:
                winner_participant = await BattleParticipant.objects.filter(
                    battle=battle,
                    discord_id=battle.last_hitter_id,
                    is_alive=True
                ).afirst()
            if not winner_participant:
                await battle.asave()
                return await interaction.followup.send(
                    "Last hitter is dead or disqualified. Battle concluded with no winner.",
                    ephemeral=True
                )
        elif winner == "RNG" and alive_participants:
            winner_participant = random.choice(alive_participants)
        
        if winner_participant and winner != "NONE":
            battle.winner_id = winner_participant.discord_id
            await battle.asave()
            
            boss_special = await Special.objects.filter(name="Boss").afirst()
            if not boss_special:
                return await interaction.followup.send(
                    "ERROR: 'Boss' special not found! Please create it in the admin panel.",
                    ephemeral=True
                )
            
            player, _ = await Player.get_or_create(discord_id=winner_participant.discord_id)
            
            instance = await BallInstance.create(
                ball=battle.boss_ball,
                player=player,
                special=boss_special,
                attack_bonus=0,
                health_bonus=0
            )
            
            winner_user = await self.bot.fetch_user(winner_participant.discord_id)
            
            await interaction.followup.send(
                f"Boss battle concluded! Winner: {winner_user}",
                ephemeral=True
            )
            
            await interaction.channel.send(
                f"# Boss has been defeated! {self.bot.get_emoji(battle.boss_ball.emoji_id)}\n"
                f"<@{winner_participant.discord_id}> has won the Boss Battle!\n\n"
                f"`Boss` `{battle.boss_ball.country}` {settings.collectible_name} awarded!"
            )
            
            await log_action(
                f"**BOSS CONCLUDED**: {winner_user} won the {battle.boss_ball.country} battle ({winner})",
                self.bot,
                (await BossSettings.load()).log_channel_id
            )
        else:
            await battle.asave()
            await interaction.followup.send("Boss battle concluded with no winner.", ephemeral=True)
            
            if alive_participants:
                await interaction.channel.send(
                    f"# Boss has been defeated! {self.bot.get_emoji(battle.boss_ball.emoji_id)}\n"
                    f"The boss has been defeated, but no winner was declared!"
                )
            else:
                await interaction.channel.send(
                    f"# Boss is victorious! {self.bot.get_emoji(battle.boss_ball.emoji_id)}\n"
                    f"All challengers have fallen!"
                )
        
        all_participants = [p async for p in BattleParticipant.objects.filter(battle=battle)]
        stats_text = "**Final Stats:**\n\n"
        
        for p in all_participants:
            user = await self.bot.fetch_user(p.discord_id)
            status = "✅" if p.is_alive else "💀"
            stats_text += f"{status} {user}: **{p.total_damage_dealt:,}** damage dealt\n"
        
        if len(stats_text) < 1900:
            await interaction.channel.send(stats_text)

    @bossadmin.command(name="hackjoin")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def hackjoin(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
        user_id: str | None = None
    ):
        """
        Manually add a player to the boss battle
        
        Parameters
        ----------
        user: discord.User
            The user to add
        user_id: str
            User ID to add (alternative to user parameter)
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        if (user and user_id) or (not user and not user_id):
            return await interaction.followup.send(
                "You must provide either `user` or `user_id`.",
                ephemeral=True
            )
        
        if not user:
            try:
                user = await self.bot.fetch_user(int(user_id))
            except (ValueError, discord.NotFound):
                return await interaction.followup.send(
                    "Invalid or not found user ID.",
                    ephemeral=True
                )
        
        battle = await BossBattle.objects.filter(is_active=True).afirst()
        if not battle:
            return await interaction.followup.send("No active boss battle.", ephemeral=True)
        
        exists = await BattleParticipant.objects.filter(
            battle=battle,
            discord_id=user.id
        ).aexists()
        
        if exists:
            return await interaction.followup.send(
                f"{user} is already in the battle!",
                ephemeral=True
            )
        
        disqualified = await DisqualifiedPlayer.objects.filter(
            battle=battle,
            discord_id=user.id
        ).afirst()
        
        if disqualified:
            await disqualified.adelete()
        
        player, _ = await Player.get_or_create(discord_id=user.id)
        await BattleParticipant.objects.acreate(
            battle=battle,
            player=player,
            discord_id=user.id
        )
        
        await interaction.followup.send(
            f"{user} has been added to the boss battle!",
            ephemeral=True
        )
        
        await log_action(
            f"{user} was hackjoined to the battle by {interaction.user}",
            self.bot,
            (await BossSettings.load()).log_channel_id
        )

    @bossadmin.command(name="disqualify")
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def disqualify(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
        user_id: str | None = None,
        reason: str = "No reason provided",
        undisqualify: bool = False
    ):
        """
        Disqualify or undisqualify a player from the boss battle
        
        Parameters
        ----------
        user: discord.User
            The user to disqualify
        user_id: str
            User ID (alternative to user parameter)
        reason: str
            Reason for disqualification
        undisqualify: bool
            Remove disqualification instead
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        if (user and user_id) or (not user and not user_id):
            return await interaction.followup.send(
                "You must provide either `user` or `user_id`.",
                ephemeral=True
            )
        
        if not user:
            try:
                user = await self.bot.fetch_user(int(user_id))
            except (ValueError, discord.NotFound):
                return await interaction.followup.send(
                    "Invalid or not found user ID.",
                    ephemeral=True
                )
        
        battle = await BossBattle.objects.filter(is_active=True).afirst()
        if not battle:
            return await interaction.followup.send("No active boss battle.", ephemeral=True)
        
        disqualified = await DisqualifiedPlayer.objects.filter(
            battle=battle,
            discord_id=user.id
        ).afirst()
        
        if undisqualify:
            if disqualified:
                await disqualified.adelete()
                return await interaction.followup.send(
                    f"{user} has been undisqualified. Use `/boss admin hackjoin` to re-add them.",
                    ephemeral=True
                )
            else:
                return await interaction.followup.send(
                    f"{user} is not disqualified.",
                    ephemeral=True
                )
        
        if disqualified:
            return await interaction.followup.send(
                f"{user} is already disqualified. Set `undisqualify` to True to remove.",
                ephemeral=True
            )
        
        await DisqualifiedPlayer.objects.acreate(
            battle=battle,
            discord_id=user.id,
            reason=reason
        )
        
        participant = await BattleParticipant.objects.filter(
            battle=battle,
            discord_id=user.id
        ).afirst()
        
        if participant and participant.is_alive:
            participant.is_alive = False
            participant.died_at = datetime.now()
            await participant.asave()
        
        await interaction.followup.send(
            f"{user} has been disqualified: {reason}",
            ephemeral=True
        )
        
        await log_action(
            f"{user} was disqualified by {interaction.user}: {reason}",
            self.bot,
            (await BossSettings.load()).log_channel_id
        )

    @app_commands.command()
    async def select(
        self,
        interaction: discord.Interaction,
        countryball: BallInstanceTransform,
        special: SpecialEnabledTransform | None = None
    ):
        """
        Select a countryball to use for the current round
        
        Parameters
        ----------
        countryball: BallInstance
            The countryball to use
        special: Special
            Filter autocomplete by special (optional)
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        battle = await BossBattle.objects.filter(is_active=True).afirst()
        if not battle:
            return await interaction.followup.send("No active boss battle.", ephemeral=True)
        
        if not battle.is_picking:
            return await interaction.followup.send(
                f"It's not time to select a {settings.collectible_name} yet!",
                ephemeral=True
            )
        
        participant = await BattleParticipant.objects.filter(
            battle=battle,
            discord_id=interaction.user.id,
            is_alive=True
        ).afirst()
        
        if not participant:
            return await interaction.followup.send(
                "You haven't joined, or you're dead/disqualified.",
                ephemeral=True
            )
        
        action_exists = await RoundAction.objects.filter(
            battle=battle,
            participant=participant,
            round_number=battle.current_round
        ).aexists()
        
        if action_exists:
            return await interaction.followup.send(
                f"You've already selected a {settings.collectible_name} this round!",
                ephemeral=True
            )
        
        if not countryball.is_tradeable:
            return await interaction.followup.send(
                f"This {settings.collectible_name} cannot be used!",
                ephemeral=True
            )
        
        boss_settings = await BossSettings.load()
        
        ball_atk = min(max(countryball.attack, 0), boss_settings.max_atk)
        ball_hp = min(max(countryball.health, 0), boss_settings.max_hp)
        
        is_shiny = countryball.shiny
        
        if is_shiny:
            ball_atk += boss_settings.shiny_atk_bonus
            ball_hp += boss_settings.shiny_hp_bonus
        
        if battle.is_attack_round:
            damage_taken = battle.boss_attack_amount
            damage_dealt = 0
            
            if damage_taken >= ball_hp:
                participant.is_alive = False
                participant.died_at = datetime.now()
                participant.total_damage_taken += damage_taken
                await participant.asave()
                
                result_msg = f"Your {countryball.description(short=True, bot=self.bot)} had **{ball_hp:,} HP** and died!"
            else:
                participant.total_damage_taken += damage_taken
                await participant.asave()
                
                result_msg = f"Your {countryball.description(short=True, bot=self.bot)} had **{ball_hp:,} HP** and survived!"
        else:
            damage_dealt = ball_atk
            damage_taken = 0
            
            battle.current_hp -= damage_dealt
            battle.last_hitter_id = interaction.user.id
            await battle.asave()
            
            participant.total_damage_dealt += damage_dealt
            await participant.asave()
            
            result_msg = f"Your {countryball.description(short=True, bot=self.bot)} dealt **{damage_dealt:,}** damage!"
        
        await RoundAction.objects.acreate(
            battle=battle,
            participant=participant,
            round_number=battle.current_round,
            ball_used_id=countryball.id,
            damage_dealt=damage_dealt,
            damage_taken=damage_taken
        )
        
        shiny_text = f" (✨ +{boss_settings.shiny_atk_bonus} ATK, +{boss_settings.shiny_hp_bonus} HP)" if is_shiny else ""
        
        await interaction.followup.send(
            f"{countryball.description(short=True, include_emoji=True, bot=self.bot)} selected!\n"
            f"**ATK:** {ball_atk:,} | **HP:** {ball_hp:,}{shiny_text}\n\n"
            f"{result_msg}",
            ephemeral=True
        )
        
        await log_action(
            f"Round {battle.current_round}: {interaction.user} - {result_msg}",
            self.bot,
            (await BossSettings.load()).log_channel_id
        )

    @app_commands.command()
    async def stats(self, interaction: discord.Interaction):
        """
        View your stats for the current boss battle
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        battle = await BossBattle.objects.filter(is_active=True).afirst()
        if not battle:
            return await interaction.followup.send("No active boss battle.", ephemeral=True)
        
        participant = await BattleParticipant.objects.filter(
            battle=battle,
            discord_id=interaction.user.id
        ).afirst()
        
        if not participant:
            return await interaction.followup.send(
                "You haven't joined the current boss battle or have no stats yet.", 
                ephemeral=True
            )
            
        status_emoji = "✅ Alive" if participant.is_alive else "💀 Dead"
        
        await interaction.followup.send(
            f"**Your Boss Battle Stats ({battle.boss_ball.country}):**\n"
            f"> **Status:** {status_emoji}\n"
            f"> **Total Damage Dealt:** {participant.total_damage_dealt:,}\n"
            f"> **Total Damage Taken:** {participant.total_damage_taken:,}",
            ephemeral=True
        )
