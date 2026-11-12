"""Патч там, де функцію визначено, а не там, де її шукає код: справжній SMTP і ConnectionRefusedError.

pytest demos/test_wrong_patch.py
"""
from unittest import mock

from newsapp import alerts


def test_patch_where_defined() -> None:
    with mock.patch("newsapp.mail.send_email", return_value="id-7"):
        assert alerts.alert_editor("Уряд ухвалив бюджет") == "id-7"
