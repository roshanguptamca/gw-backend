from unittest.mock import patch

from django.apps import apps


def test_securewise_worker_command_does_not_start_futurewise_scheduler(monkeypatch):
    monkeypatch.setattr("sys.argv", ["manage.py", "securewise_worker"])
    future_wise_config = apps.get_app_config("future_wise")

    with (
        patch("django.db.backends.signals.connection_created.connect"),
        patch("apps.future_wise.apps._start_background_scheduler") as start_scheduler,
    ):
        future_wise_config.ready()

    start_scheduler.assert_not_called()
