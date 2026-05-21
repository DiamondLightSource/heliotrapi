import asyncio
import logging
import time
from datetime import datetime
from uuid import UUID

from xrpd_toolbox.utils.messenger import DEFAULT_DII_PROCESSED_DESTINATION, Messenger

from indigoapi.analysis_core.registry import get_analysis
from indigoapi.models import AnalysisRequest, AnalysisResult
from indigoapi.serialisers import serialise

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QueueManager:
    def __init__(self, workers: int = 2, messenger: Messenger | None = None):
        self.queue: asyncio.Queue[AnalysisRequest] = asyncio.Queue(maxsize=0)  # 0 = inf
        self.results: dict[UUID, tuple[AnalysisResult, float]] = {}
        self.workers = workers
        self.latest_result: AnalysisResult | None = None
        self.messenger = messenger

        logger.info(self.queue)

    async def enqueue(self, job: AnalysisRequest):
        job.created_at = datetime.now()
        logger.info(job)
        await self.queue.put(job)

    async def worker(self):
        while True:
            job = await self.queue.get()

            try:
                analysis_fn = get_analysis(job.analysis_name)

                result_value = await analysis_fn(**job.inputs)

                # Convert numpy and other non-JSON-serializable types
                result_value = serialise(result_value)

                analysis_result = AnalysisResult(
                    request_id=job.request_id,
                    analysis_name=job.analysis_name,
                    status="completed",
                    result=result_value,
                    created_at=job.created_at,
                    finished_at=datetime.now(),
                )

            except Exception as e:
                analysis_result = AnalysisResult(
                    request_id=job.request_id,
                    analysis_name=job.analysis_name,
                    status="failed",
                    result=str(e),
                    created_at=job.created_at,
                    finished_at=datetime.now(),
                )

                if self.messenger is not None:
                    self.messenger.send_message(
                        DEFAULT_DII_PROCESSED_DESTINATION,
                        analysis_result.model_dump_json(),
                    )

            self.results[job.request_id] = (analysis_result, time.time())
            # store latest result
            self.latest_result = analysis_result
