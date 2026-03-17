from django.apps import AppConfig

class BossConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "boss"
    verbose_name = "Boss Battles"
    dpy_package = "boss.boss"