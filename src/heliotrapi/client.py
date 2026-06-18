import json
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

import requests

from heliotrapi.api.endpoints import (
    ANALYSE_ROUTE,
    ANALYSES_ROUTE,
    ENDPOINTS_ROUTE,
    HEALTH_ROUTE,
    RESULT_BY_ID_ROUTE,
    RESULT_LATEST_ROUTE,
    RESULTS_ALL_ROUTE,
    STREAM_ROUTE,
)
from heliotrapi.logger import logger
from heliotrapi.models import AnalysisRequest, AnalysisResponse, AnalysisResult
from heliotrapi.utils.serialisers import serialise


class AnalysisClient:
    """
    Python client for the Analysis API
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        session: requests.Session | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.latest_request_id: UUID | None = None
        self.session = session or requests.Session()

    def available_analyses(
        self, as_strings: bool = True
    ) -> list[dict[str, Any]] | list[str]:
        resp = self.session.get(f"{self.base_url}{ANALYSES_ROUTE}")
        resp.raise_for_status()
        analyses = resp.json()
        if as_strings:
            return [self._format_analysis_signature(analysis) for analysis in analyses]
        return analyses

    def _format_analysis_signature(self, analysis: dict[str, Any]) -> str:
        params = []
        for param in analysis.get("parameters", []):
            param_str = f"{param['name']}: {param['annotation']}"
            if param.get("default") is not None:
                param_str += f" = {param['default']}"
            params.append(param_str)

        annotations = analysis.get("annotations", "Any")
        if params:
            params_block = ",\n        ".join(params)
            signature = (
                f"{analysis['name']}(\n        {params_block},\n    ) -> {annotations}:"
            )
        else:
            signature = f"{analysis['name']}() -> {annotations}:"

        return signature

    def health(self) -> dict[str, Any]:
        resp = self.session.get(f"{self.base_url}{HEALTH_ROUTE}")
        resp.raise_for_status()
        return resp.json()

    def submit(self, analysis: str | Callable, **inputs: Any) -> UUID:
        """
        Submit an analysis job.

        Example:
        client.submit("gaussian_fit", x=x, y=y)
        """

        inputs = serialise(inputs)

        analysis_name = (
            analysis.__name__ if isinstance(analysis, Callable) else analysis
        )

        analysis_request = AnalysisRequest(analysis_name=analysis_name, inputs=inputs)
        json = analysis_request.model_dump(mode="json")

        resp = self.session.post(f"{self.base_url}{ANALYSE_ROUTE}", json=json)

        resp.raise_for_status()  # raise for 404 or other non-200 errors

        analysis_response = AnalysisResponse.model_validate(resp.json())
        analysis_response.is_accepted()  # will raise if not accepted

        request_id = UUID(resp.json()["request_id"])
        self.latest_request_id = request_id

        return request_id

    def request_result(self, request_id: UUID) -> AnalysisResult | None:

        route = RESULT_BY_ID_ROUTE.format(request_id=request_id)
        resp = self.session.get(f"{self.base_url}{route}")

        if resp.status_code == 404:
            return None

        resp.raise_for_status()
        response = resp.json()

        return AnalysisResult.model_validate(response)

    def get_result(
        self,
        timeout: float = 5.0,
        poll_interval: float = 0.1,
    ) -> AnalysisResult:

        start_time = time.time()

        while True:
            try:
                resp = self.session.get(f"{self.base_url}{RESULT_LATEST_ROUTE}")
                resp.raise_for_status()
                return AnalysisResult.model_validate(resp.json())

            except Exception as e:
                logger.error(e)
                time.sleep(poll_interval)

                if (timeout > 0) and (time.time() - start_time > timeout):
                    return AnalysisResult(
                        status="error",
                        analysis_name="",
                        inputs={},
                        result=None,
                        created_at=datetime.now(),
                        finished_at=datetime.now(),
                    )

    def get_last_submitted_result(
        self,
        timeout: float = 5.0,
        poll_interval: float = 0.1,
    ) -> AnalysisResult:

        if self.latest_request_id is None:
            return AnalysisResult(
                status="error",
                analysis_name="",
                inputs={},
                result=None,
                created_at=datetime.now(),
                finished_at=datetime.now(),
            )

        return self.get_request_id_result(
            self.latest_request_id,
            timeout,
            poll_interval,
        )

    def get_endpoints(self):
        resp = self.session.get(f"{self.base_url}{ENDPOINTS_ROUTE}")
        resp.raise_for_status()
        return resp.json()

    def get_all_results(self):
        resp = self.session.get(f"{self.base_url}{RESULTS_ALL_ROUTE}")
        resp.raise_for_status()
        return resp.json()

    def get_request_id_result(
        self,
        request_id: UUID,
        timeout: float = 30.0,
        poll_interval: float = 0.1,
    ) -> AnalysisResult:

        start_time = time.time()

        while True:
            result = self.request_result(request_id)

            if result is not None:
                return result

            if time.time() - start_time > timeout:
                raise TimeoutError(f"Result not ready after {timeout} seconds")

            time.sleep(poll_interval)

    def start_stream(self) -> UUID:
        pass

    def stream_results(self, request_id: UUID):

        stream_route = STREAM_ROUTE.format(request_id=request_id)
        stream_url = f"{self.base_url}{stream_route}"

        with self.session.get(stream_url, stream=True) as resp:
            resp.raise_for_status()

            event_type = None

            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue

                # event type
                if line.startswith("event:"):
                    event_type = line.replace("event: ", "").strip()

                # data payload
                elif line.startswith("data:"):
                    payload = line.replace("data: ", "").strip()

                    if event_type == "update":
                        yield json.loads(payload)

                    elif event_type == "done":
                        return


if __name__ == "__main__":
    # client = AnalysisClient("http://i15-1-analysis.diamond.ac.uk")
    # print(client.get_all_results())
    import matplotlib.pyplot as plt

    client = AnalysisClient()

    client.submit(analysis="double", number=5)

    print(client.get_result())

    client.start_stream()

    x_data = []
    y_data = []

    plt.ion()
    fig, ax = plt.subplots()

    for point in client.stream_results():
        x_data.append(point["x"])
        y_data.append(point["y"])

        ax.clear()
        ax.plot(x_data, y_data)
        ax.set_title("Live SSE Analysis Plot")

        plt.pause(0.01)
