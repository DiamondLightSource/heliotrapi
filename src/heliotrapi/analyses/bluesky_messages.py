from heliotrapi import logger
from heliotrapi.analysis_core.decorator import (
    start_message_analysis,
)
from heliotrapi.task_queue.message_models import StartMessage


@start_message_analysis
def log_start(mymessage: StartMessage):

    instrument = mymessage.doc.instrument
    instrument_session = mymessage.doc.instrument_session
    scan_file = mymessage.doc.scan_file
    plan_name = mymessage.doc.plan_name

    logger.info(
        f"RunStart Detected on {instrument}, {instrument_session}, {scan_file} with {plan_name}"  # noqa
    )

    return


# @finished_nexus_analysis
# def process_nexus(message: NexusMessage):
#     filepath = message.filePath

#     logger.info(f"{filepath} has not been processed.")
