"""
authcore/migrations/0001_initial.py
Auto-generated initial migration for User and BehaviorLog models.
Run with: python manage.py migrate
"""

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        # ── Create the custom User table (no password field used) ──────────
        migrations.CreateModel(
            name='User',
            fields=[
                ('password',     models.CharField(max_length=128, verbose_name='password')),
                ('is_superuser', models.BooleanField(default=False)),
                ('id',           models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email',        models.EmailField(max_length=254, unique=True)),
                ('username',     models.CharField(max_length=50, unique=True)),
                ('created_at',   models.DateTimeField(default=django.utils.timezone.now)),
                ('last_login',   models.DateTimeField(blank=True, null=True)),
                ('is_active',    models.BooleanField(default=True)),
                ('is_staff',     models.BooleanField(default=False)),
                ('groups',       models.ManyToManyField(blank=True, related_name='authcore_user_groups', to='auth.group')),
                ('user_permissions', models.ManyToManyField(blank=True, related_name='authcore_user_permissions', to='auth.permission')),
            ],
            options={
                'verbose_name': 'User',
                'db_table': 'users',
            },
        ),

        # ── Create the BehaviorLog table ────────────────────────────────────
        migrations.CreateModel(
            name='BehaviorLog',
            fields=[
                ('id',              models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('typing_speed',    models.FloatField(help_text='Avg characters per second')),
                ('key_hold_time',   models.FloatField(help_text='Avg key hold duration in ms')),
                ('mouse_velocity',  models.FloatField(help_text='Avg mouse speed in px/sec')),
                ('click_interval',  models.FloatField(help_text='Avg ms between clicks')),
                ('scroll_depth',    models.FloatField(help_text='Fraction of page scrolled (0-1)')),
                ('network_latency', models.FloatField(help_text='Network latency in ms')),
                ('device_hash',     models.CharField(max_length=64)),
                ('location_hash',   models.CharField(max_length=64)),
                ('time_of_day',     models.IntegerField(help_text='Hour of day (0-23, UTC)')),
                ('was_trusted',     models.BooleanField(default=False)),
                ('trust_score',     models.IntegerField(default=0)),
                ('created_at',      models.DateTimeField(auto_now_add=True)),
                ('user',            models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='behavior_logs',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Behavior Log',
                'db_table': 'behavior_logs',
                'ordering': ['-created_at'],
            },
        ),

        # ── Add the performance index on (user, created_at) ─────────────────
        migrations.AddIndex(
            model_name='behaviorlog',
            index=models.Index(fields=['user', '-created_at'], name='behavior_lo_user_id_idx'),
        ),
    ]
