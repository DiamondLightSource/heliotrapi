import json
from collections import deque
from pathlib import Path
from shutil import copy2
from time import sleep

import stomp
from pydantic import BaseModel

DEFAULT_BROKER = "rabbitmq"
DEFAULT_DESTINATIONS = [
    "/topic/public.worker.event",
    "/topic/gda.messages.scan",
]

DEFAULT_DII_UI_PLOT_DESTINATION = (
    "/topic/public.data.plot"  # Currently prone to change as of 07/05/26
)

DEFAULT_DII_PROCESSED_DESTINATION = "/topic/public.data.processed"

TIMEOUT = 1  # in seconds


class MessageUnpacker:
    messages = deque()

    @staticmethod
    def unpack_dict(unpacked: dict):
        for key, value in unpacked.items():
            if isinstance(value, dict):
                MessageUnpacker.unpack_dict(value)
            else:
                MessageUnpacker.messages.append(f"{key}: {value}")

        return MessageUnpacker.messages


class ScanListener(stomp.ConnectionListener):
    def __init__(self, maxlen=100):
        self.messages = deque(maxlen=maxlen)

    def on_error(self, message):  # type: ignore
        print(f"received an error: {message}")

    def on_message(self, message):  # type: ignore
        message_body: dict = json.loads(message.body)
        self.messages.append(message_body)


class Messenger:
    def __init__(
        self,
        beamline: str | None = None,
        host: str | None = None,
        broker: str | None = DEFAULT_BROKER,
        port: int = 61613,
        username: str | None = None,
        password: str | None = None,
        destinations: Path | list[Path] | str | list[str] | None = None,
        auto_connect: bool = True,
        auto_subscribe: bool = True,
        **kwargs,
    ):
        self.beamline = beamline
        self.host = host
        self.port = port
        self.broker = broker
        self.port = port

        self.username = username
        self.password = password
        self.auto_connect = auto_connect
        self.auto_subscribe = auto_subscribe
        self.destinations = destinations

        # /topic/public.worker.event blueapi
        # defined here https://github.com/DiamondLightSource/blueapi/blob/77129d132d5481b9d6adad3fe15c02d581aff9f7/docs/reference/asyncapi.yaml#L4

        # "/topic/gda.messages.scan"  # nexus file converter
        # defined here: https://gitlab.diamond.ac.uk/daq/d2acq/services/nexus-file-converter/-/blob/master/src/main/resources/application.yaml

        if (beamline is not None) and (not beamline.startswith("i")):
            print(f"{beamline} must start with i, eg i15-1, or i11")

        if not self.destinations:
            print(f"No destination specified, defaulting to {DEFAULT_DESTINATIONS}")
            self.destinations = DEFAULT_DESTINATIONS

        if self.host and self.port:
            print("Both host and port specified, using host and port")
        elif self.beamline and not self.host:
            self.broker = DEFAULT_BROKER
            print("Host not specified, constructing from beamline name")
            self.host = f"{self.beamline}-{self.broker}-daq.diamond.ac.uk"
        else:
            raise ValueError("Either host or beamline must be provided")

        self.messages = deque()
        self.scan_listener = ScanListener()

        self.run = True

        if self.auto_connect:
            try:
                self.setup_connection()
                self.connect()
            except Exception:
                print(f"Could not connect to {self.host}")
        if self.auto_subscribe:
            try:
                self.subscribe()
            except Exception:
                print(f"Could not subscribe to {self.destinations}")

    def setup_connection(self):
        self.conn = stomp.Connection(
            host_and_ports=[(self.host, self.port)],
            auto_content_length=False,
            heartbeats=(TIMEOUT * 1000, TIMEOUT * 1000),  # heartbeat in in ms
            timeout=TIMEOUT,
        )

        self.conn.set_listener("scan_listener", self.scan_listener)

    def connect(self):
        print("Connecting..")

        if self.username and self.password:
            self.conn.connect(self.username, self.password, wait=True)
        else:
            self.conn.connect(wait=True)

        print("Connected to STOMP server at", self.host, self.port)

    def disconnect(self):
        self.conn.disconnect()

    def subscribe(self):
        if isinstance(self.destinations, list):
            for i, dest in enumerate(self.destinations):
                self.conn.subscribe(destination=dest, id=i + 1, ack="auto")
        else:
            self.conn.subscribe(destination=self.destinations, id=1, ack="auto")

    def send_file(self, path: str):
        """Use this when you want dawn to open and plot a file"""
        message = json.dumps({"filePath": path})
        destination = "/topic/org.dawnsci.file.topic"
        self.send_message(destination, message)

    def send_start(self, path: str):
        """use this in when doing live processing and it has started"""
        message = json.dumps(
            {"filePath": path, "status": "STARTED", "swmrStatus": "ENABLED"}
        )
        destination = "/topic/gda.messages.processing"
        self.send_message(destination, message)

    def send_update(self, path):
        """use this in when doing live processing and it has started"""

        message = json.dumps(
            {"filePath": path, "status": "UPDATED", "swmrStatus": "ACTIVE"}
        )
        destination = "/topic/gda.messages.processing"
        self.send_message(destination, message)

    def send_finished(self, path):
        message = json.dumps(
            {"filePath": path, "status": "FINISHED", "swmrStatus": "ACTIVE"}
        )
        destination = "/topic/gda.messages.processing"
        self.send_message(destination, message)

    def send_message(self, destination: str, message: str):
        try:
            self.conn.send(destination=destination, body=message, ack="auto")
            print(f"Message sent to: {destination}")
        except Exception:
            print("Could not send message!")

    def stop(self):
        """Stop listening to destinations"""
        self.run = False

    def get_message(self):
        return self.scan_listener.messages.popleft()

    def send_plot_data(self, plot_data: BaseModel | str):
        """Pass this a PlotData object and it will serialise it
        and send it to RabbitMQ telling the UI to plot it"""

        if isinstance(plot_data, BaseModel):
            plot_message = plot_data.model_dump_json()
        else:
            plot_message = plot_data

        self.send_message(DEFAULT_DII_UI_PLOT_DESTINATION, plot_message)

    def send_processed_data(self, processed_data: BaseModel | str):
        """Pass this a result object and it will serialise it
        and send it to RabbitMQ telling the bluesky what to do next"""

        if isinstance(processed_data, BaseModel):
            processed_message = processed_data.model_dump_json()
        else:
            processed_message = processed_data

        self.send_message(DEFAULT_DII_PROCESSED_DESTINATION, processed_message)

    def listen(self, max_iter: int = 50, interval: float | int = 1.0):
        c = 0
        self.run = True

        while (self.run is True) and (c < max_iter):
            if self.scan_listener.messages:
                print("Processing message:", self.scan_listener.messages.popleft())
            sleep(interval)
            c += 1

    def send_to_ispyb(self, original_filepath: str, filepath_out: str) -> None:
        p = Path(original_filepath)
        magic_path = p.parent / ".ispyb" / (p.stem + "_mythen_nx/data.dat")
        copy2(filepath_out, magic_path)  # copies to ispyb


# if __name__ == "__main__":
#     client = Messenger("i15-1", broker="rabbitmq", username="guest", password="guest")

#     print("djsdnsj")

#     print(client.host)

#     client._send_message("/topic/public.worker.event", "fff")
