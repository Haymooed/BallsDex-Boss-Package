from django.contrib import admin
from django.utils import timezone

from .models import BossSettings, BossBattle, BattleParticipant, RoundAction, DisqualifiedPlayer


@admin.register(BossSettings)
class BossSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "shiny_atk_bonus",
        "shiny_hp_bonus",
        "max_atk",
        "max_hp",
        "min_boss_damage",
        "max_boss_damage",
        "log_channel_id"
    )
    fieldsets = (
        ("Shiny Bonuses", {
            "fields": ("shiny_atk_bonus", "shiny_hp_bonus")
        }),
        ("Stat Caps", {
            "fields": ("max_atk", "max_hp")
        }),
        ("Boss Damage Range", {
            "fields": ("min_boss_damage", "max_boss_damage")
        }),
        ("Logging", {
            "fields": ("log_channel_id",)
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
    
    def changelist_view(self, request, extra_context=None):
        if not BossSettings.objects.filter(pk=1).exists():
            BossSettings.objects.create(pk=1)
        return super().changelist_view(request, extra_context)
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        if not BossSettings.objects.filter(pk=1).exists():
            BossSettings.objects.create(pk=1)
        return super().change_view(request, object_id, form_url, extra_context)


class BattleParticipantInline(admin.TabularInline):
    model = BattleParticipant
    extra = 0
    readonly_fields = (
        "player",
        "discord_id",
        "total_damage_dealt",
        "total_damage_taken",
        "joined_at",
        "died_at"
    )
    can_delete = False
    fields = (
        "player",
        "discord_id",
        "is_alive",
        "total_damage_dealt",
        "total_damage_taken",
        "joined_at",
        "died_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


class DisqualifiedPlayerInline(admin.TabularInline):
    model = DisqualifiedPlayer
    extra = 0
    readonly_fields = ("disqualified_at",)
    fields = ("discord_id", "reason", "disqualified_at")
    can_delete = True


@admin.register(BossBattle)
class BossBattleAdmin(admin.ModelAdmin):
    list_display = (
        "boss_ball",
        "current_round",
        "current_hp",
        "initial_hp",
        "is_active",
        "winner_display",
        "created_at"
    )
    list_filter = ("is_active", "is_attack_round", "winner_type", "created_at")
    search_fields = ("boss_ball__country",)
    readonly_fields = ("created_at", "ended_at")
    inlines = (BattleParticipantInline, DisqualifiedPlayerInline)
    actions = (
        "action_end_battle",
        "action_start_attack_round",
        "action_start_defend_round",
        "action_end_round",
        "action_reset_round_state",
        "action_clear_winner",
    )

    fieldsets = (
        ("Boss", {"fields": ("boss_ball", "initial_hp", "current_hp")}),
        ("Round state", {"fields": ("current_round", "is_active", "is_picking", "is_attack_round", "boss_attack_amount")}),
        ("Weather & images", {"fields": ("weather", "start_image_url", "defend_image_url", "attack_image_url")}),
        ("Winner", {"fields": ("winner_id", "winner_type", "last_hitter_id")}),
        ("Timestamps", {"fields": ("created_at", "ended_at")}),
    )

    def has_add_permission(self, request):
        return False

    def winner_display(self, obj):
        if obj.winner_id:
            return f"Player {obj.winner_id} ({obj.get_winner_type_display()})"
        return "No winner yet"
    winner_display.short_description = "Winner"

    @admin.action(description="End battle (set inactive, stop picking)")
    def action_end_battle(self, request, queryset):
        now = timezone.now()
        queryset.update(is_active=False, is_picking=False, ended_at=now)

    @admin.action(description="Start attack round (picking=true, attack=true, +1 round)")
    def action_start_attack_round(self, request, queryset):
        for battle in queryset:
            if not battle.is_active:
                continue
            battle.is_picking = True
            battle.is_attack_round = True
            battle.current_round += 1
            battle.save(update_fields=("is_picking", "is_attack_round", "current_round"))

    @admin.action(description="Start defend round (picking=true, attack=false, +1 round)")
    def action_start_defend_round(self, request, queryset):
        for battle in queryset:
            if not battle.is_active:
                continue
            battle.is_picking = True
            battle.is_attack_round = False
            battle.current_round += 1
            battle.save(update_fields=("is_picking", "is_attack_round", "current_round"))

    @admin.action(description="End round (picking=false)")
    def action_end_round(self, request, queryset):
        queryset.update(is_picking=False)

    @admin.action(description="Reset round state (picking=false, attack=false, boss_attack_amount=0)")
    def action_reset_round_state(self, request, queryset):
        queryset.update(is_picking=False, is_attack_round=False, boss_attack_amount=0)

    @admin.action(description="Clear winner fields")
    def action_clear_winner(self, request, queryset):
        queryset.update(winner_id=None, winner_type=None, last_hitter_id=None)


@admin.register(BattleParticipant)
class BattleParticipantAdmin(admin.ModelAdmin):
    list_display = (
        "discord_id",
        "battle",
        "is_alive",
        "total_damage_dealt",
        "total_damage_taken",
        "joined_at"
    )
    list_filter = ("is_alive", "battle__is_active")
    search_fields = ("discord_id", "battle__boss_ball__country")
    readonly_fields = ("joined_at",)
    actions = ("action_revive", "action_kill", "action_reset_stats")

    def has_add_permission(self, request):
        return False

    @admin.action(description="Revive selected participants")
    def action_revive(self, request, queryset):
        queryset.update(is_alive=True, died_at=None)

    @admin.action(description="Kill selected participants")
    def action_kill(self, request, queryset):
        queryset.update(is_alive=False, died_at=timezone.now())

    @admin.action(description="Reset damage dealt/taken")
    def action_reset_stats(self, request, queryset):
        queryset.update(total_damage_dealt=0, total_damage_taken=0)


@admin.register(RoundAction)
class RoundActionAdmin(admin.ModelAdmin):
    list_display = (
        "participant",
        "battle",
        "round_number",
        "damage_dealt",
        "damage_taken",
        "created_at"
    )
    list_filter = ("round_number", "battle")
    search_fields = ("participant__discord_id", "battle__boss_ball__country")
    readonly_fields = (
        "battle",
        "participant",
        "round_number",
        "ball_used_id",
        "damage_dealt",
        "damage_taken",
        "created_at"
    )

    def has_add_permission(self, request):
        return False


@admin.register(DisqualifiedPlayer)
class DisqualifiedPlayerAdmin(admin.ModelAdmin):
    list_display = ("discord_id", "battle", "reason", "disqualified_at")
    list_filter = ("battle__is_active", "disqualified_at")
    search_fields = ("discord_id", "reason", "battle__boss_ball__country")
    readonly_fields = ("disqualified_at",)

    def has_add_permission(self, request):
        return True
