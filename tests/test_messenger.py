from unittest.mock import MagicMock

import pytest

from heliotrapi.utils.messenger import Messenger, ScanListener


def test_messenger_initialisation_with_beamline_only():
    messenger = Messenger(beamline="i15-1")
    assert messenger.host == "i15-1-rabbitmq-daq.diamond.ac.uk"
    assert messenger.broker == "rabbitmq"


def test_messenger_initialisation_with_host_only():
    messenger = Messenger(host="i15-1-rabbitmq-daq.diamond.ac.uk")
    assert messenger.host == "i15-1-rabbitmq-daq.diamond.ac.uk"
    assert messenger.port == 61613


def test_messenger_initialisation_with_host_and_port():
    messenger = Messenger(host="i15-1-rabbitmq-daq.diamond.ac.uk", port=12345)
    assert messenger.host == "i15-1-rabbitmq-daq.diamond.ac.uk"
    assert messenger.port == 12345


def test_messenger_initialisation_with_host_and_beamline():
    messenger = Messenger(host="i15-1-control", broker="activemq")
    assert messenger.host == "i15-1-control"
    assert messenger.broker == "activemq"


def test_scan_listener_on_message():
    listener = ScanListener()

    class Message:
        body = '{"a": 1}'

    listener.on_message(Message())

    assert listener.messages[0] == {"a": 1}


def test_assert_fails_when_requires_host_or_beamline():
    with pytest.raises(ValueError):
        Messenger(
            auto_connect=False,
            auto_subscribe=False,
        )


def test_send_message(monkeypatch):
    fake_conn = MagicMock()

    monkeypatch.setattr(
        "heliotrapi.utils.messenger.stomp.Connection",
        lambda *args, **kwargs: fake_conn,
    )

    messenger = Messenger(
        beamline="i15-1",
        auto_connect=False,
        auto_subscribe=False,
    )

    messenger.setup_connection()

    messenger.send_message("/topic/test", "hello")

    fake_conn.send.assert_called_once_with(
        destination="/topic/test",
        body="hello",
        ack="auto",
    )
