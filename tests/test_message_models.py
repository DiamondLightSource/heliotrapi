import pytest

from heliotrapi.task_queue.message_models import (
    DescriptorMessage,
    EventMessage,
    NexusMessage,
    StartMessage,
    StopMessage,
    StreamDatumMessage,
    StreamResourceMessage,
    validate_stomp_message,
)

START_MESSAGE = {
    "name": "start",
    "doc": {
        "uid": "4e6741e0-be66-4899-8794-e372021cd617",
        "time": 1781265581.4665747,
        "versions": {
            "ophyd": "1.11.1",
            "ophyd_async": "0.17a6.dev1+g8423cca51.d20260611",
            "bluesky": "1.15.0",
            "event_model": "1.23.1",
        },
        "instrument": "i15-1",
        "user": "Unknown",
        "instrument_session": "cm44163-3",
        "tiled_access_tags": ['{"proposal": 44163, "visit": 3, "beamline": "i15-1"}'],
        "data_session_directory": "/dls/i15-1/data/2026/cm44163-3",
        "detector_file_template": "{instrument}-{scan_id}-{device_name}",
        "scan_file": "i15-1-96680",
        "scan_id": 96680,
        "plan_type": "generator",
        "plan_name": "static_collection_plan",
    },
    "task_id": "a3b4dd7c-017f-4adc-b9cc-07bb7548bb97",
}
DESCRIPTOR_MESSAGE = {
    "name": "descriptor",
    "doc": {
        "configuration": {
            "tth": {
                "data": {
                    "tth-offset": 0.0,
                    "tth-velocity": 16.647684118553,
                    "tth-motor_egu": "deg",
                },
                "timestamps": {
                    "tth-offset": 1781265561.515749,
                    "tth-velocity": 1781265561.515749,
                    "tth-motor_egu": 1781265561.515749,
                },
                "data_keys": {
                    "tth-offset": {
                        "dtype": "number",
                        "shape": [],
                        "dtype_numpy": "<f8",
                        "source": "ca://BL15J-MO-TABLE-01:TTH.OFF",
                        "units": "deg",
                        "precision": 5,
                        "limits": {
                            "control": {"low": -1e300, "high": 1e300},
                            "display": {"low": -1e300, "high": 1e300},
                        },
                    },
                    "tth-velocity": {
                        "dtype": "number",
                        "shape": [],
                        "dtype_numpy": "<f8",
                        "source": "ca://BL15J-MO-TABLE-01:TTH.VELO",
                        "units": "deg/sec",
                        "precision": 5,
                        "limits": {
                            "control": {"low": 0.0, "high": 16.647684118553},
                            "display": {"low": 0.0, "high": 16.647684118553},
                        },
                    },
                    "tth-motor_egu": {
                        "dtype": "string",
                        "shape": [],
                        "dtype_numpy": "|S40",
                        "source": "ca://BL15J-MO-TABLE-01:TTH.EGU",
                    },
                },
            },
            "xtal": {"data": {}, "timestamps": {}, "data_keys": {}},
            "robot-spinner": {"data": {}, "timestamps": {}, "data_keys": {}},
        },
        "data_keys": {
            "tth": {
                "dtype": "number",
                "shape": [],
                "dtype_numpy": "<f8",
                "source": "ca://BL15J-MO-TABLE-01:TTH.RBV",
                "units": "deg",
                "precision": 5,
                "limits": {
                    "control": {"low": -33.1, "high": 103.1},
                    "display": {"low": -33.1, "high": 103.1},
                },
                "object_name": "tth",
            },
            "xtal-energy_kev": {
                "dtype": "number",
                "shape": [],
                "dtype_numpy": "<f8",
                "source": "derived://xtal-energy_kev",
                "object_name": "xtal",
            },
            "robot-spinner": {
                "dtype": "string",
                "shape": [],
                "dtype_numpy": "|S40",
                "source": "derived://robot-spinner",
                "choices": ["Spinner On", "Spinner Off"],
                "object_name": "robot-spinner",
            },
        },
        "name": "baseline",
        "object_keys": {
            "tth": ["tth"],
            "xtal": ["xtal-energy_kev"],
            "robot-spinner": ["robot-spinner"],
        },
        "run_start": "4e6741e0-be66-4899-8794-e372021cd617",
        "time": 1781265581.635631,
        "uid": "8af7bb64-10c2-489d-9404-cc3141cb9b0d",
        "hints": {"tth": {"fields": ["tth"]}, "xtal": {"fields": ["xtal-energy_kev"]}},
    },
    "task_id": "a3b4dd7c-017f-4adc-b9cc-07bb7548bb97",
}
EVENT_MESSAGE = {
    "name": "event",
    "doc": {
        "uid": "d45c80f8-4ebe-47e3-8ae8-118e0cae07ec",
        "time": 1781265581.8614416,
        "data": {
            "robot-spinner": "Spinner Off",
            "tth": 90.7651481105,
            "xtal-energy_kev": 40.05,
        },
        "timestamps": {
            "robot-spinner": 1780928736.574397,
            "tth": 1781265561.515749,
            "xtal-energy_kev": 1781263870.507539,
        },
        "seq_num": 1,
        "filled": {},
        "descriptor": "8af7bb64-10c2-489d-9404-cc3141cb9b0d",
    },
    "task_id": "a3b4dd7c-017f-4adc-b9cc-07bb7548bb97",
}
STREAM_RESOURCE_MESSAGE = {
    "name": "stream_resource",
    "doc": {
        "uid": "6f1cbf20-caf3-4c12-9d65-16f2a87c0ecb",
        "data_key": "fastcs_eiger",
        "mimetype": "application/x-hdf5",
        "uri": "file://localhost/dls/i15-1/data/2026/cm44163-3/i15-1-96680-fastcs_eiger.h5_000001.h5",
        "parameters": {"chunk_shape": [1, 512, 1028], "dataset": "/data"},
        "run_start": "4e6741e0-be66-4899-8794-e372021cd617",
    },
    "task_id": "a3b4dd7c-017f-4adc-b9cc-07bb7548bb97",
}
STREAM_DATUM_MESSAGE = {
    "name": "stream_datum",
    "doc": {
        "stream_resource": "6f1cbf20-caf3-4c12-9d65-16f2a87c0ecb",
        "uid": "6f1cbf20-caf3-4c12-9d65-16f2a87c0ecb/0",
        "seq_nums": {"start": 1, "stop": 2},
        "indices": {"start": 0, "stop": 1},
        "descriptor": "66848e81-e7ac-47e2-b4be-4360795a1f45",
    },
    "task_id": "a3b4dd7c-017f-4adc-b9cc-07bb7548bb97",
}
STOP_MESSAGE = {
    "name": "stop",
    "doc": {
        "uid": "a5af9bbc-13d6-4d1f-aaab-ed076935b4a5",
        "time": 1781265600.6895273,
        "run_start": "4e6741e0-be66-4899-8794-e372021cd617",
        "exit_status": "success",
        "reason": "",
        "num_events": {"baseline": 2, "primary": 1},
    },
    "task_id": "a3b4dd7c-017f-4adc-b9cc-07bb7548bb97",
}


STARTED_NEXUS_MESSAGE = {
    "status": "STARTED",
    "filePath": "/dls/i15-1/data/2026/cm44163-3/i15-1-96780.nxs",
    "visitDirectory": "/dls/i15-1/data/2026/cm44163-3",
    "swmrStatus": "ENABLED",
    "scanNumber": -1754420994,
    "scanDimensions": [-1],
    "scannables": [],
    "detectors": [],
    "percentageComplete": -1.0,
    "processingRequest": {},
}

FINISHED_NEXUS_MESSAGE = {
    "status": "FINISHED",
    "filePath": "/dls/i15-1/data/2026/cm44163-3/i15-1-96779.nxs",
    "visitDirectory": "/dls/i15-1/data/2026/cm44163-3",
    "swmrStatus": "ENABLED",
    "scanNumber": -1839618421,
    "scanDimensions": [-1],
    "scannables": [],
    "detectors": [],
    "percentageComplete": -1.0,
    "processingRequest": {},
}


@pytest.mark.parametrize(
    "message, expected_type",
    [
        (START_MESSAGE, StartMessage),
        (DESCRIPTOR_MESSAGE, DescriptorMessage),
        (EVENT_MESSAGE, EventMessage),
        (STREAM_RESOURCE_MESSAGE, StreamResourceMessage),
        (STREAM_DATUM_MESSAGE, StreamDatumMessage),
        (STOP_MESSAGE, StopMessage),
        (STARTED_NEXUS_MESSAGE, NexusMessage),
        (FINISHED_NEXUS_MESSAGE, NexusMessage),
    ],
)
def test_validate_stomp_message(message: dict, expected_type: type):
    model = validate_stomp_message(message)

    assert model is not None
    assert isinstance(model, expected_type)
