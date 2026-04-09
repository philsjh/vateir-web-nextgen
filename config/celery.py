import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery(os.environ.get("APP_NAME", "vateir"))
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    # Poll the VATSIM live data feed every 20 seconds
    "poll-live-feed-every-20s": {
        "task": "apps.controllers.tasks.poll_live_feed",
        "schedule": 20.0,
    },
    # Fetch METARs for configured airports every 5 minutes
    "fetch-metars-every-5m": {
        "task": "apps.public.tasks.fetch_metars",
        "schedule": 300.0,
    },
    # Update all controller stats once a day at 03:00 UTC
    "update-all-controller-stats-daily": {
        "task": "apps.controllers.tasks.update_all_controller_stats",
        "schedule": crontab(hour=3, minute=0),
    },
    # Sync roster from VATSIM API daily at 02:00 UTC
    "sync-roster-daily": {
        "task": "apps.controllers.tasks.sync_roster",
        "schedule": crontab(hour=2, minute=0),
    },
    # Check ticket SLA every 30 minutes
    "check-ticket-sla-every-30m": {
        "task": "apps.tickets.tasks.check_ticket_sla",
        "schedule": crontab(minute="*/30"),
    },
    # Sync endorsements, visitors, and roster from VATEUD Core API every 6 hours
    "sync-vateud-every-6h": {
        "task": "apps.controllers.tasks.sync_vateud",
        "schedule": crontab(hour="*/6", minute=15),
    },
}
