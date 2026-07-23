import numpy as np
from fastapi.testclient import TestClient

from heliotrapi.analyses.peak_fitting import gaussian, gaussian_fit
from heliotrapi.analyses.simple_maths import sine_wave
from heliotrapi.client import AnalysisClient
from heliotrapi.server import start_api


def test_gaussian_fit_with_client():
    np.random.seed(1)

    x = np.linspace(-5, 5, 200)
    true_amp, true_center, true_sigma = 3.0, 1.2, 0.8
    y = gaussian(x, true_amp, true_center, true_sigma)
    assert isinstance(y, np.ndarray)
    y_noisy = y + np.random.rand(y.shape[-1]) / 5

    app = start_api()

    # Use context manager to trigger lifespan
    with TestClient(app) as client_http:
        # Now queue_manager exists
        client = AnalysisClient(base_url=str(client_http.base_url), session=client_http)  # type: ignore

        # Submit job
        client.submit(gaussian_fit.__name__, x=x, y=y_noisy)
        result = client.get_result()

        # Validate results
        res = result.result
        assert abs(res["amplitude"] - true_amp) < 0.2
        assert abs(res["position"] - true_center) < 0.2
        assert abs(res["width"] - true_sigma) < 0.2


def test_client_lists_analyses():

    app = start_api()

    # Use context manager to trigger lifespan
    with TestClient(app) as client_http:
        # Now queue_manager exists
        client = AnalysisClient(base_url=str(client_http.base_url), session=client_http)  # type: ignore

        client.available_analyses()


def test_client_lists_analyses_as_strings():

    app = start_api()

    with TestClient(app) as client_http:
        client = AnalysisClient(base_url=str(client_http.base_url), session=client_http)  # type: ignore

        signatures = client.available_analyses(as_strings=True)

        assert isinstance(signatures, list)
        assert any(isinstance(sig, str) for sig in signatures)
        assert any(sig.startswith("gaussian_fit(") for sig in signatures)  # type: ignore
        assert any("->" in sig for sig in signatures)


def test_client_runs_argument_with_none():

    app = start_api()

    with TestClient(app) as client_http:
        client = AnalysisClient(base_url=str(client_http.base_url), session=client_http)  # type: ignore

        _ = client.submit(sine_wave.__name__, array=None)

        result = client.get_result()

        assert len(result.result) == 100


def test_stream_results():

    app = start_api()

    with TestClient(app) as client_http:
        client = AnalysisClient(base_url=str(client_http.base_url), session=client_http)  # type: ignore

        count = 0

        for _ in client.stream_results(
            analysis="beam_energy_to_wavelength", beam_energy=15, max_iterations=10
        ):
            count = count + 1
        assert count == 10
