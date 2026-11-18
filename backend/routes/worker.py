from celery import Celery
from celery.schedules import crontab

celery = Celery(
    "Exortal",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
    include=["routes.tasks"],
)

celery.conf.update(
    timezone="Asia/Kolkata",
    enable_utc=False,
    task_publish_retry=False,
    beat_schedule={
        "daily-examination-reminders": {
            "task": "routes.tasks.daily_reminders",
            "schedule": crontab(hour=9, minute=0),
        },
        "monthly-examination-report": {
            "task": "routes.tasks.send_monthly_report",
            "schedule": crontab(day_of_month=1, hour=9, minute=0),
        },
    },
)
