from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("boss", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="bossbattle",
            name="weather",
            field=models.CharField(
                choices=[
                    ("CLEAR", "Clear"),
                    ("STORM", "Storm (weaker common balls)"),
                    ("BLESS", "Blessing (stronger rare balls)"),
                    ("FOG", "Fog (weaker ultra-rare balls)"),
                ],
                default="CLEAR",
                help_text="Weather condition affecting rarity-based modifiers",
                max_length=10,
            ),
        ),
    ]

