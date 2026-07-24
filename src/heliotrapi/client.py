import json
import time
from collections.abc import Callable, Generator
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx

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
from heliotrapi.models import (
    AnalysisRequest,
    AnalysisResponse,
    AnalysisResult,
    AnalysisStream,
    AnalysisStreamRequest,
    StreamUpdate,
)
from heliotrapi.utils.serialisers import serialise


class AnalysisClient:
    """
    Python client for the Analysis API
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        session: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.latest_request_id: UUID | None = None
        self.session = session or httpx.Client()

    def available_analyses(
        self, as_strings: bool = True
    ) -> list[dict[str, Any]] | list[str]:
        """returns a list of all the analyses that can be submitted"""
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
        """checks the API is alive - returns status: ok if it is"""
        resp = self.session.get(f"{self.base_url}{HEALTH_ROUTE}")
        resp.raise_for_status()
        return resp.json()

    def submit_analysis_request(
        self, analysis_request: AnalysisRequest
    ) -> AnalysisResponse:

        json_payload = analysis_request.model_dump(mode="json")
        resp = self.session.post(f"{self.base_url}{ANALYSE_ROUTE}", json=json_payload)
        resp.raise_for_status()  # raise for 404 or other non-200 errors
        analysis_response = AnalysisResponse.model_validate(resp.json())

        return analysis_response

    def submit(self, analysis: str | Callable, **inputs: Any) -> UUID:
        """
        Submit an analysis job.

        Example:
        client.submit("gaussian_fit", x=x, y=y)
        """

        inputs = serialise(inputs)

        analysis_name = self._get_analysis_name(analysis)

        analysis_request = AnalysisRequest(analysis_name=analysis_name, inputs=inputs)

        analysis_response = self.submit_analysis_request(analysis_request)

        analysis_response.is_accepted()  # will raise if not accepted

        assert analysis_response.request_id is not None

        request_id = analysis_response.request_id
        self.latest_request_id = request_id

        return request_id

    def request_result(self, request_id: UUID) -> AnalysisResult | None:
        """Requests a result once - with a given request_id
        - doesn't guareteee to return a result
        ie if the job hasn't finished"""

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
        """Get the last completed result that has been submitted -
        even if YOU didn't submit it. The last result may not be the result you want
        ie if the job you last submitted hasn't finished"""

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
        """Get the result that this client last submitted.
        If this client hasn't submitted any it will raise"""

        if self.latest_request_id is None:
            raise ValueError("You have not submitted any analyses!")

        return self.get_request_id_result(
            self.latest_request_id,
            timeout,
            poll_interval,
        )

    def get_endpoints(self):
        """get all available endpoitns"""

        resp = self.session.get(f"{self.base_url}{ENDPOINTS_ROUTE}")
        resp.raise_for_status()
        return resp.json()

    def get_all_results(self):
        """get all the results that are current stored in memory"""
        resp = self.session.get(f"{self.base_url}{RESULTS_ALL_ROUTE}")
        resp.raise_for_status()
        return resp.json()

    def get_request_id_result(
        self,
        request_id: UUID,
        timeout: float = 30.0,
        poll_interval: float = 0.1,
    ) -> AnalysisResult:
        """get a specific result, but requesting the result with a given request_id"""

        start_time = time.time()

        while True:
            result = self.request_result(request_id)

            if result is not None:
                return result

            if time.time() - start_time > timeout:
                raise TimeoutError(f"Result not ready after {timeout} seconds")

            time.sleep(poll_interval)

    def _get_analysis_name(self, analysis: str | Callable):

        analysis_name = (
            analysis.__name__ if isinstance(analysis, Callable) else analysis
        )

        return analysis_name

    def stream_results(
        self,
        analysis: str | Callable,
        max_iterations: int = 100,
        update_interval: float = 0.1,
        **kwargs: Any,
    ) -> Generator[StreamUpdate]:
        """This will open up a server side event,
        and keep getting results from a particular analysis job"""

        inputs = serialise(kwargs)

        analysis_name = self._get_analysis_name(analysis)

        analysis_request = AnalysisStreamRequest(
            analysis_name=analysis_name,
            inputs=inputs,
            update_interval=update_interval,
            max_iterations=max_iterations,
        )

        analysis_request_json = analysis_request.model_dump(mode="json")

        stream_url = f"{self.base_url}{STREAM_ROUTE}"

        with self.session.stream("GET", stream_url, json=analysis_request_json) as resp:
            resp.raise_for_status()

            event_type = None

            for line in resp.iter_lines():
                if not line:
                    continue

                line: str

                # event type
                if line.startswith("event:"):
                    event_type = line.replace("event: ", "").strip()

                # data payload
                elif line.startswith("data:"):
                    payload = line.replace("data: ", "").strip()

                    if event_type == "update":
                        yield StreamUpdate.model_validate(json.loads(payload))

                    elif event_type == "done":
                        return

    def plot_stream(
        self,
        analysis: str | Callable,
        update_interval: float = 0.1,
        max_iterations=100,
        **kwargs: Any,
    ):

        import matplotlib.pyplot as plt  # type: ignore

        analysis_name = self._get_analysis_name(analysis)

        plt.ion()
        fig, ax = plt.subplots()

        stream = AnalysisStream()

        try:
            for stream_update in self.stream_results(
                analysis=analysis_name,
                max_iterations=max_iterations,
                update_interval=update_interval,
                **kwargs,
            ):
                print(stream_update)

                stream_update: StreamUpdate

                stream.append(stream_update)

                ax.clear()
                ax.plot(stream["x"], stream["y"])
                ax.set_title(analysis_name)
                fig.canvas.draw()
                fig.canvas.flush_events()

        except Exception as e:
            ax.clear()
            plt.close()
            raise Exception(e) from e

        plt.close()

        return stream


# if __name__ == "__main__":
#     # client = AnalysisClient("http://i15-1-analysis.diamond.ac.uk")
#     # print(client.get_all_results())

#     client = AnalysisClient()

#     client.submit(analysis="b_iso_to_u_iso", b_iso=[5])

#     print(client.get_result())

#     stream = client.plot_stream(
#         analysis="beam_energy_to_wavelength", beam_energy=25, max_iterations=10
#     )

#     assert len(stream.x) == 10

#     for stream_update in client.stream_results(
#         analysis="beam_energy_to_wavelength", beam_energy=15, max_iterations=10
#     ):
#         print(stream_update)
