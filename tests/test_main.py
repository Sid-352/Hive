"""
tests/test_main.py
Unit tests for lightweight safety helpers in app/main.py.
"""

from app.main import _sanitize_receive_filename


def test_sanitize_keeps_normal_filename():
    assert _sanitize_receive_filename("report.pdf") == "report.pdf"


def test_sanitize_strips_directory_components():
    assert _sanitize_receive_filename("../secret.txt") == "secret.txt"
    assert _sanitize_receive_filename(r"..\secret.txt") == "secret.txt"


def test_sanitize_replaces_empty_or_dot_values():
    assert _sanitize_receive_filename("") == "received_file"
    assert _sanitize_receive_filename(".") == "received_file"
    assert _sanitize_receive_filename("..") == "received_file"


def test_sanitize_handles_none_input():
    assert _sanitize_receive_filename(None) == "received_file"

