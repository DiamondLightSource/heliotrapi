import json
from collections import deque
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
from pydantic import BaseModel

from heliotrapi.utils.messenger import (
    DEFAULT_DESTINATIONS,
    DEFAULT_DII_PROCESSED_DESTINATION,
    DEFAULT_DII_UI_PLOT_DESTINATION,
    MessageUnpacker,
    Messenger,
    ScanListener,
)


@pytest.fixture
def mock_connection(mocker):
    conn = Mock()
    mocker.patch("heliotrapi.utils.messenger.stomp.Connection", return_value=conn)
    return conn


@pytest.fixture
def messenger(mock_connection):
    return Messenger(
        host="localhost",
        auto_connect=False,
        auto_subscribe=False,
    )


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


def test_unpack_dict_flat():
    MessageUnpacker.messages = deque()

    result = MessageUnpacker.unpack_dict({"a": 1, "b": 2})

    assert list(result) == ["a: 1", "b: 2"]


def test_unpack_dict_nested():
    MessageUnpacker.messages = deque()

    result = MessageUnpacker.unpack_dict(
        {
            "outer": {
                "x": 1,
                "y": 2,
            },
            "z": 3,
        }
    )

    assert list(result) == ["x: 1", "y: 2", "z: 3"]


def test_scan_listener_on_error(capsys):
    listener = ScanListener()

    listener.on_error("boom")

    captured = capsys.readouterr()
    assert "received an error: boom" in captured.out


def test_scan_listener_on_message():
    listener = ScanListener()

    msg = Mock()
    msg.body = json.dumps({"a": 1})

    listener.on_message(msg)

    assert listener.messages.pop() == {"a": 1}


def test_scan_listener_maxlen():
    listener = ScanListener(maxlen=1)

    m1 = Mock()
    m1.body = json.dumps({"a": 1})

    m2 = Mock()
    m2.body = json.dumps({"b": 2})

    listener.on_message(m1)
    listener.on_message(m2)

    assert len(listener.messages) == 1
    assert listener.messages[0] == {"b": 2}


def test_init_with_invalid_beamline(capsys):
    Messenger(
        beamline="bad",
        host="localhost",
        auto_connect=False,
        auto_subscribe=False,
    )

    assert "must start with i" in capsys.readouterr().out


def test_init_default_destinations(capsys):
    m = Messenger(
        host="localhost",
        auto_connect=False,
        auto_subscribe=False,
    )

    assert m.destinations == DEFAULT_DESTINATIONS
    assert "defaulting to" in capsys.readouterr().out


def test_init_construct_host_from_beamline():
    m = Messenger(
        beamline="i15-1",
        auto_connect=False,
        auto_subscribe=False,
    )

    assert m.host == "i15-1-rabbitmq-daq.diamond.ac.uk"


def test_init_raises_without_host_or_beamline():
    with pytest.raises(ValueError):
        Messenger(
            host=None,
            beamline=None,
            auto_connect=False,
            auto_subscribe=False,
        )


def test_init_auto_connect_failure(mocker, capsys):
    mocker.patch.object(
        Messenger,
        "setup_connection",
        side_effect=Exception("fail"),
    )

    Messenger(
        host="localhost",
        auto_connect=True,
        auto_subscribe=False,
    )

    assert "Could not connect" in capsys.readouterr().out


def test_init_auto_subscribe_failure(mocker, capsys):
    mocker.patch.object(Messenger, "subscribe", side_effect=Exception())

    Messenger(
        host="localhost",
        auto_connect=False,
        auto_subscribe=True,
    )

    assert "Could not subscribe" in capsys.readouterr().out


def test_setup_connection(mock_connection, messenger):
    messenger.setup_connection()

    mock_connection.set_listener.assert_called_once()


def test_connect_with_credentials(mock_connection, messenger, capsys):
    messenger.setup_connection()

    messenger.username = "user"
    messenger.password = "pass"

    messenger.connect()

    mock_connection.connect.assert_called_once_with(
        "user",
        "pass",
        wait=True,
    )

    assert "Connected to STOMP server" in capsys.readouterr().out


def test_connect_without_credentials(mock_connection, messenger):
    messenger.setup_connection()

    messenger.connect()

    mock_connection.connect.assert_called_once_with(wait=True)


def test_disconnect(mock_connection, messenger):
    messenger.setup_connection()

    messenger.disconnect()

    mock_connection.disconnect.assert_called_once()


def test_subscribe_single_destination(mock_connection, messenger):
    messenger.setup_connection()

    messenger.destinations = "/topic/test"

    messenger.subscribe()

    mock_connection.subscribe.assert_called_once_with(
        destination="/topic/test",
        id=1,
        ack="auto",
    )


def test_subscribe_multiple_destinations(mock_connection, messenger):
    messenger.setup_connection()

    messenger.destinations = ["/a", "/b"]

    messenger.subscribe()

    assert mock_connection.subscribe.call_count == 2

    mock_connection.subscribe.assert_any_call(
        destination="/a",
        id=1,
        ack="auto",
    )

    mock_connection.subscribe.assert_any_call(
        destination="/b",
        id=2,
        ack="auto",
    )


def test_send_file(messenger, mocker):
    send = mocker.patch.object(messenger, "send_message")

    messenger.send_file("/tmp/file")

    send.assert_called_once_with(
        "/topic/org.dawnsci.file.topic",
        json.dumps({"filePath": "/tmp/file"}),
    )


def test_send_start(messenger, mocker):
    send = mocker.patch.object(messenger, "send_message")

    messenger.send_start("/tmp/file")

    send.assert_called_once()


def test_send_update(messenger, mocker):
    send = mocker.patch.object(messenger, "send_message")

    messenger.send_update("/tmp/file")

    send.assert_called_once()


def test_send_finished(messenger, mocker):
    send = mocker.patch.object(messenger, "send_message")

    messenger.send_finished("/tmp/file")

    send.assert_called_once()


def test_send_message_success(mock_connection, messenger, capsys):
    messenger.setup_connection()

    messenger.send_message("/dest", "hello")

    mock_connection.send.assert_called_once_with(
        destination="/dest",
        body="hello",
        ack="auto",
    )

    assert "Message sent to: /dest" in capsys.readouterr().out


def test_send_message_failure(mock_connection, messenger, capsys):
    messenger.setup_connection()

    mock_connection.send.side_effect = Exception()

    messenger.send_message("/dest", "hello")

    assert "Could not send message!" in capsys.readouterr().out


def test_stop(messenger):
    messenger.run = True

    messenger.stop()

    assert messenger.run is False


def test_get_message(messenger):
    messenger.scan_listener.messages.append("abc")

    assert messenger.get_message() == "abc"


class ExampleModel(BaseModel):
    value: int


def test_send_plot_data_model(messenger, mocker):
    send = mocker.patch.object(messenger, "send_message")

    messenger.send_plot_data(ExampleModel(value=5))

    send.assert_called_once_with(
        DEFAULT_DII_UI_PLOT_DESTINATION,
        '{"value":5}',
    )


def test_send_plot_data_string(messenger, mocker):
    send = mocker.patch.object(messenger, "send_message")

    messenger.send_plot_data("hello")

    send.assert_called_once_with(
        DEFAULT_DII_UI_PLOT_DESTINATION,
        "hello",
    )


def test_send_processed_data_model(messenger, mocker):
    send = mocker.patch.object(messenger, "send_message")

    messenger.send_processed_data(ExampleModel(value=5))

    send.assert_called_once_with(
        DEFAULT_DII_PROCESSED_DESTINATION,
        '{"value":5}',
    )


def test_send_processed_data_string(messenger, mocker):
    send = mocker.patch.object(messenger, "send_message")

    messenger.send_processed_data("hello")

    send.assert_called_once_with(
        DEFAULT_DII_PROCESSED_DESTINATION,
        "hello",
    )


def test_listen_processes_messages(messenger, mocker, capsys):
    mocker.patch("heliotrapi.utils.messenger.sleep")

    messenger.scan_listener.messages.append({"a": 1})

    messenger.listen(max_iter=1)

    assert "Processing message:" in capsys.readouterr().out


def test_send_to_ispyb(messenger, mocker):
    copy = mocker.patch("heliotrapi.utils.messenger.copy2")

    messenger.send_to_ispyb(
        "/tmp/test.nxs",
        "/tmp/output.dat",
    )

    expected = Path("/tmp") / ".ispyb" / "test_mythen_nx/data.dat"

    copy.assert_called_once_with(
        "/tmp/output.dat",
        expected,
    )
