from __future__ import annotations

from django.db import models
from django.utils import timezone

from bd_models.models import Ball, Player


class BossSettings(models.Model):
    singleton_id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    
    shiny_atk_bonus = models.PositiveIntegerField(
        default=1000,
        help_text="Attack bonus for shiny balls"
    )
    shiny_hp_bonus = models.PositiveIntegerField(
        default=1000,
        help_text="HP bonus for shiny balls"
    )
    max_atk = models.PositiveIntegerField(
        default=5000,
        help_text="Maximum attack stat before bonuses"
    )
    max_hp = models.PositiveIntegerField(
        default=5000,
        help_text="Maximum HP stat before bonuses"
    )
    min_boss_damage = models.PositiveIntegerField(
        default=0,
        help_text="Minimum random boss attack damage"
    )
    max_boss_damage = models.PositiveIntegerField(
        default=2000,
        help_text="Maximum random boss attack damage"
    )
    log_channel_id = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Discord channel ID for boss battle logs"
    )

    class Meta:
        verbose_name = "Boss settings"
        verbose_name_plural = "Boss settings"

    def __str__(self) -> str:
        return "Boss Settings"

    @classmethod
    async def load(cls) -> "BossSettings":
        instance, _ = await cls.objects.aget_or_create(pk=1)
        return instance


class BossBattle(models.Model):
    class Weather(models.TextChoices):
        CLEAR = "CLEAR", "Clear"
        STORM = "STORM", "Storm (weaker common balls)"
        BLESSING = "BLESS", "Blessing (stronger rare balls)"
        FOG = "FOG", "Fog (weaker ultra-rare balls)"

    boss_ball = models.ForeignKey(
        Ball,
        on_delete=models.CASCADE,
        related_name="boss_battles",
        help_text="The ball used as the boss"
    )
    initial_hp = models.PositiveIntegerField(help_text="Starting HP of the boss")
    current_hp = models.IntegerField(help_text="Current HP of the boss")
    current_round = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_picking = models.BooleanField(default=False, help_text="Whether players are currently selecting balls")
    is_attack_round = models.BooleanField(default=False, help_text="Whether this is an attack round")
    boss_attack_amount = models.PositiveIntegerField(default=0, help_text="Damage for current attack round")
    
    winner_id = models.BigIntegerField(null=True, blank=True, help_text="Discord ID of the winner")
    winner_type = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        choices=[
            ("RNG", "Random"),
            ("DMG", "Most Damage"),
            ("LAST", "Last Hitter"),
            ("NONE", "No Winner")
        ]
    )
    
    last_hitter_id = models.BigIntegerField(null=True, blank=True, help_text="Discord ID of last player to hit")
    
    start_image_url = models.URLField(null=True, blank=True)
    defend_image_url = models.URLField(null=True, blank=True)
    attack_image_url = models.URLField(null=True, blank=True)

    weather = models.CharField(
        max_length=10,
        choices=Weather.choices,
        default=Weather.CLEAR,
        help_text="Weather condition affecting attack and defense",
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Boss battle"
        verbose_name_plural = "Boss battles"

    def __str__(self) -> str:
        status = "Active" if self.is_active else "Ended"
        return f"{self.boss_ball.country} Boss Battle (Round {self.current_round}) - {status}"


class BattleParticipant(models.Model):
    battle = models.ForeignKey(
        BossBattle,
        on_delete=models.CASCADE,
        related_name="participants"
    )
    player = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name="boss_participations"
    )
    discord_id = models.BigIntegerField(help_text="Discord ID of the participant")
    is_alive = models.BooleanField(default=True)
    total_damage_dealt = models.PositiveBigIntegerField(default=0)
    total_damage_taken = models.PositiveBigIntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)
    died_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("battle", "discord_id")
        ordering = ("-total_damage_dealt",)
        verbose_name = "Battle participant"
        verbose_name_plural = "Battle participants"

    def __str__(self) -> str:
        status = "Alive" if self.is_alive else "Dead"
        return f"Player {self.discord_id} - {status} ({self.total_damage_dealt} dmg dealt)"


class RoundAction(models.Model):
    battle = models.ForeignKey(
        BossBattle,
        on_delete=models.CASCADE,
        related_name="round_actions"
    )
    participant = models.ForeignKey(
        BattleParticipant,
        on_delete=models.CASCADE,
        related_name="actions"
    )
    round_number = models.PositiveIntegerField()
    ball_used_id = models.BigIntegerField(help_text="ID of the ball instance used")
    damage_dealt = models.IntegerField(default=0, help_text="Damage dealt to boss (negative if boss attacked)")
    damage_taken = models.PositiveIntegerField(default=0, help_text="Damage taken from boss")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("round_number", "created_at")
        verbose_name = "Round action"
        verbose_name_plural = "Round actions"

    def __str__(self) -> str:
        return f"Round {self.round_number} - Player {self.participant.discord_id} - {self.damage_dealt} dmg"


class DisqualifiedPlayer(models.Model):
    battle = models.ForeignKey(
        BossBattle,
        on_delete=models.CASCADE,
        related_name="disqualifications"
    )
    discord_id = models.BigIntegerField(help_text="Discord ID of disqualified player")
    reason = models.CharField(max_length=200, blank=True)
    disqualified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("battle", "discord_id")
        ordering = ("-disqualified_at",)
        verbose_name = "Disqualified player"
        verbose_name_plural = "Disqualified players"

    def __str__(self) -> str:
        return f"Player {self.discord_id} disqualified from {self.battle}"
