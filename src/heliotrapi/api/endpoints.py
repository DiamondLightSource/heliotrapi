# NOTE: The endpoints are here and not with the routes, to avoid dependency issues
# keep these seperate to allow pip install heliotrapi[client] to not have to install
# additional dependencies

# NOTE: IF YOU CHANGE THESE YOU MUST CHANGE THE .JS FILE TOO!!!

HEALTH_ROUTE = "/healthz"
ANALYSES_ROUTE = "/get_analyses"
ENDPOINTS_ROUTE = "/endpoints"
ANALYSE_ROUTE = "/analyse"
RESULT_LATEST_ROUTE = "/results/latest"
RESULT_BY_ID_ROUTE = "/results/id/{request_id}"
RESULTS_ALL_ROUTE = "/results/all"
STREAM_ROUTE = "/results/stream/"

# NOTE: IF YOU CHANGE THESE YOU MUST CHANGE THE .JS FILE TOO!!!
