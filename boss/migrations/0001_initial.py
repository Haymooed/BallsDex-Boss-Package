from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('bd_models', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='BossSettings',
            fields=[
                ('singleton_id', models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ('shiny_atk_bonus', models.PositiveIntegerField(default=1000, help_text='Attack bonus for shiny balls')),
                ('shiny_hp_bonus', models.PositiveIntegerField(default=1000, help_text='HP bonus for shiny balls')),
                ('max_atk', models.PositiveIntegerField(default=5000, help_text='Maximum attack stat before bonuses')),
                ('max_hp', models.PositiveIntegerField(default=5000, help_text='Maximum HP stat before bonuses')),
                ('min_boss_damage', models.PositiveIntegerField(default=0, help_text='Minimum random boss attack damage')),
                ('max_boss_damage', models.PositiveIntegerField(default=2000, help_text='Maximum random boss attack damage')),
                ('log_channel_id', models.BigIntegerField(blank=True, help_text='Discord channel ID for boss battle logs', null=True)),
            ],
            options={
                'verbose_name': 'Boss settings',
                'verbose_name_plural': 'Boss settings',
            },
        ),
        migrations.CreateModel(
            name='BossBattle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('initial_hp', models.PositiveIntegerField(help_text='Starting HP of the boss')),
                ('current_hp', models.IntegerField(help_text='Current HP of the boss')),
                ('current_round', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('is_picking', models.BooleanField(default=False, help_text='Whether players are currently selecting balls')),
                ('is_attack_round', models.BooleanField(default=False, help_text='Whether this is an attack round')),
                ('boss_attack_amount', models.PositiveIntegerField(default=0, help_text='Damage for current attack round')),
                ('winner_id', models.BigIntegerField(blank=True, help_text='Discord ID of the winner', null=True)),
                ('winner_type', models.CharField(blank=True, choices=[('RNG', 'Random'), ('DMG', 'Most Damage'), ('LAST', 'Last Hitter'), ('NONE', 'No Winner')], max_length=10, null=True)),
                ('last_hitter_id', models.BigIntegerField(blank=True, help_text='Discord ID of last player to hit', null=True)),
                ('start_image_url', models.URLField(blank=True, null=True)),
                ('defend_image_url', models.URLField(blank=True, null=True)),
                ('attack_image_url', models.URLField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
                ('boss_ball', models.ForeignKey(help_text='The ball used as the boss', on_delete=django.db.models.deletion.CASCADE, related_name='boss_battles', to='bd_models.ball')),
            ],
            options={
                'verbose_name': 'Boss battle',
                'verbose_name_plural': 'Boss battles',
                'ordering': ('-created_at',),
            },
        ),
        migrations.CreateModel(
            name='BattleParticipant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('discord_id', models.BigIntegerField(help_text='Discord ID of the participant')),
                ('is_alive', models.BooleanField(default=True)),
                ('total_damage_dealt', models.PositiveBigIntegerField(default=0)),
                ('total_damage_taken', models.PositiveBigIntegerField(default=0)),
                ('joined_at', models.DateTimeField(auto_now_add=True)),
                ('died_at', models.DateTimeField(blank=True, null=True)),
                ('battle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='participants', to='boss.bossbattle')),
                ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='boss_participations', to='bd_models.player')),
            ],
            options={
                'verbose_name': 'Battle participant',
                'verbose_name_plural': 'Battle participants',
                'ordering': ('-total_damage_dealt',),
                'unique_together': {('battle', 'discord_id')},
            },
        ),
        migrations.CreateModel(
            name='RoundAction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('round_number', models.PositiveIntegerField()),
                ('ball_used_id', models.BigIntegerField(help_text='ID of the ball instance used')),
                ('damage_dealt', models.IntegerField(default=0, help_text='Damage dealt to boss (negative if boss attacked)')),
                ('damage_taken', models.PositiveIntegerField(default=0, help_text='Damage taken from boss')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('battle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='round_actions', to='boss.bossbattle')),
                ('participant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='actions', to='boss.battleparticipant')),
            ],
            options={
                'verbose_name': 'Round action',
                'verbose_name_plural': 'Round actions',
                'ordering': ('round_number', 'created_at'),
            },
        ),
        migrations.CreateModel(
            name='DisqualifiedPlayer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('discord_id', models.BigIntegerField(help_text='Discord ID of disqualified player')),
                ('reason', models.CharField(blank=True, max_length=200)),
                ('disqualified_at', models.DateTimeField(auto_now_add=True)),
                ('battle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='disqualifications', to='boss.bossbattle')),
            ],
            options={
                'verbose_name': 'Disqualified player',
                'verbose_name_plural': 'Disqualified players',
                'ordering': ('-disqualified_at',),
                'unique_together': {('battle', 'discord_id')},
            },
        ),
    ]
