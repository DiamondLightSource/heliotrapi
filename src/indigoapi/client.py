import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

import numpy as np
import requests

from indigoapi.api.routes import (
    ANALYSE_ROUTE,
    ANALYSES_ROUTE,
    ENDPOINTS_ROUTE,
    HEALTH_ROUTE,
    RESULT_BY_ID_ROUTE,
    RESULT_LATEST_ROUTE,
    RESULTS_ALL_ROUTE,
)
from indigoapi.models import AnalysisRequest, AnalysisResult
from indigoapi.utils.serialisers import serialise

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

        resp.raise_for_status()

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

        return AnalysisResult(**response)

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


if __name__ == "__main__":
    import numpy as np

    from indigoapi.analyses.peak_fitting import gaussian

    x = np.linspace(0, 20, 200)

    y = gaussian(x, 10, 5, 1) + (np.random.rand(x.shape[-1]) / 5)

    client = AnalysisClient()

    for i in range(5):
        id = client.submit("double", number=i)
        result = client.get_request_id_result(id)
    # client.submit("gaussian_fit", x=x, y=y)

    # client.submit("beam_energy_to_wavelength", beam_energy=15)

    for i in client.get_all_results():
        print(i, "\n")

    available_analyses = client.available_analyses(as_strings=True)

    for analysis in available_analyses:
        print(analysis)

    # print(client.get_endpoints())
    # for i in client.list_analyses()[0:4]:
    #     print(i)
