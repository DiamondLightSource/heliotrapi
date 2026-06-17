from heliotrapi.analysis_core.decorator import (
    start_message_analysis,
)
from heliotrapi.logging import logger
from heliotrapi.task_queue.message_models import StartMessage


@start_message_analysis
def log_start(message: StartMessage):

    instrument = message.doc.instrument
    instrument_session = message.doc.instrument_session
    scan_file = message.doc.scan_file
    plan_name = message.doc.plan_name

    logger.info(
        f"RunStart Detected on {instrument}, {instrument_session}, {scan_file} with {plan_name}"  # noqa
    )

    return


# @finished_nexus_analysis
# def process_nexus(message: NexusMessage):
#     filepath = message.filePath

#     logger.info(f"{filepath} has not been processed.")
