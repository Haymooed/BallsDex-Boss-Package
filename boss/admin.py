from django.contrib import admin
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
        "is_alive",
        "total_damage_dealt",
        "total_damage_taken",
        "joined_at",
        "died_at"
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class DisqualifiedPlayerInline(admin.TabularInline):
    model = DisqualifiedPlayer
    extra = 0
    readonly_fields = ("discord_id", "reason", "disqualified_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


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
    readonly_fields = (
        "boss_ball",
        "initial_hp",
        "current_hp",
        "current_round",
        "is_active",
        "is_picking",
        "is_attack_round",
        "boss_attack_amount",
        "winner_id",
        "winner_type",
        "last_hitter_id",
        "created_at",
        "ended_at"
    )
    inlines = (BattleParticipantInline, DisqualifiedPlayerInline)

    def has_add_permission(self, request):
        return False

    def winner_display(self, obj):
        if obj.winner_id:
            return f"Player {obj.winner_id} ({obj.get_winner_type_display()})"
        return "No winner yet"
    winner_display.short_description = "Winner"


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
    readonly_fields = (
        "battle",
        "player",
        "discord_id",
        "is_alive",
        "total_damage_dealt",
        "total_damage_taken",
        "joined_at",
        "died_at"
    )

    def has_add_permission(self, request):
        return False


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
    readonly_fields = ("battle", "discord_id", "reason", "disqualified_at")

    def has_add_permission(self, request):
        return False
