# NOTE: The endpoints are here and not with the routes, to avoid dependency issues
# keep these seperate to allow pip install heliotrapi[client] to not have to install
# additional dependencies

HEALTH_ROUTE = "/healthz"
ANALYSES_ROUTE = "/get_analyses"
ANALYSE_ROUTE = "/analyse"
RESULT_LATEST_ROUTE = "/results/latest"
RESULT_BY_ID_ROUTE = "/results/{request_id}"
ENDPOINTS_ROUTE = "/endpoints"
RESULTS_ALL_ROUTE = "/results/all"
RESULTS_ALL_ROUTE = "/results/all"
STREAM_ROUTE = "/strean"
