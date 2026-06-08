[![CI](https://github.com/DiamondLightSource/heliotrapi/actions/workflows/ci.yml/badge.svg)](https://github.com/DiamondLightSource/heliotrapi/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/DiamondLightSource/heliotrapi/branch/main/graph/badge.svg)](https://codecov.io/gh/DiamondLightSource/heliotrapi)
[![PyPI](https://img.shields.io/pypi/v/heliotrapi.svg)](https://pypi.org/project/heliotrapi)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

# heliotrapi

An API for small fast data analysis jobs at Diamond Light Source.

[HEE-LEE-OH-TRAY-PEE-EYE]

Helio - Like the sun, a very brilliant light source
Heliotrope - An pink-purple indigo-like colour
HeliotrAPI - The API that comes after blue

`heliotrapi` exposes an HTTP API to submit analysis jobs, return queued results, and optionally consume messages from RabbitMQ.

Source          | <https://github.com/DiamondLightSource/heliotrapi>
:---:           | :---:
PyPI            | `pip install heliotrapi`
Docker          | `docker run ghcr.io/diamondlightsource/heliotrapi:latest`
Releases        | <https://github.com/DiamondLightSource/heliotrapi/releases>

Example Python usage:

```python
from heliotrapi import __version__

print(f"Hello heliotrapi {__version__}")
```

To start the api server in dev mode on local host:

```bash
uvicorn heliotrapi.main:start_api --reload --factory --host 127.0.0.1 --port 8000

or

heliotrapi serve

```

## Overview

The app accepts analysis jobs via HTTP or the client and stores results in memory for a configurable time-to-live. Jobs can also be ingested from RabbitMQ if `rabbitmq.enabled` is set.

## Sending/Recieving results using the python client

```python

from heliotrapi.client import AnalysisClient

client = AnalysisClient("https://ixx-analysis.diamond.ac.uk")

print(client.available_analyses()) #see available analyses

request_id = client.submit("name_of_analysis", examplekwarg1=1, examplekwarg2=2) # <- if kawrgs are invalid it will raise

result = client.get_result() #returns an AnalysisResult basemodel

result = client.get_request_id_result(request_id) #same as above, but specific

print(result)

```

## Sending/Recieving results as an http request

submit jobs to `/analyse` as a json blob via an HTTP POST request

if want to call the function "double" eg:

```python
def double(number: float | int) -> float:
    """Example analysis that doubles a number."""
    return number * 2
```

then the json would be sent as a POST request like:

{"analysis_name": "double", "inputs": {"number": 5}}

the server will handle request_id time and created_at, 
but if you want you can also send it in it's full form 
and create a uuid and timestamp yourself:

{"analysis_name":"double","inputs":{"number":5},"request_id":"d68de927-79f5-4df3-83d9-d125445c758a","created_at":"2026-05-29T11:47:09.087317"}

via curl the example command would be:

```bash
curl -X POST https://ixx-analysis.diamond.ac.uk/analyse -H "Content-Type: application/json" -d '{"analysis_name":"double","inputs":{"number":5}}'
```

and to get the last result from `/result/latest` as a GET request

```bash
curl -X GET https://i15-1-analysis.diamond.ac.uk/result/latest
```

If you are getting redirected due to the a proxy use curl -LX ...

## Using the WebUI

You can also navigate to the url or the ip address to be met with:

![Web UI](images/webui.png)

### Request flow

- AnalysisClient submits jobs to `/analyse`
- Jobs are queued in `QueueManager`
- Workers process jobs in FIFO order
- Results are returned via `/result/id/{request_id}` or `/result/latest`
- Optional RabbitMQ listener can enqueue jobs automatically

                     AnalysisClient ─────--────────────────
                        │ ▲                │              │
                        ▼ │                ▼              ▼
        Analysis <-── heliotrapi ──---►  RabbitMQ ──---► Results
           Job   ─---►    ▲                │
                          │                │
                          │                │   
                    RabbitListener <───────

## Using your plugin code

In the config or thhe helm chart you can changed the following lines:

```yaml
    plugins:
      paths:
        - ./plugins # local folder for plugins
      github_repos: # list of Https GitHub repos with analysis code (ending with .git)
        - https://github.com/DiamondLightSource/xrpd-toolbox.git
      register_all: True # whether to register all analyses found in plugins or only those decorated
```

In this example plugins will be downloaded and installed to ./plugins. The github repo https://github.com/DiamondLightSource/xrpd-toolbox.git
will be cloned to the .plugins folder, and because register_all is True all of them will be added to heliotrapi's available analyses. Alternativey
You can selectively add analyses to the api by adding a decorator to your function, in the repo.

## Kubernetes deployment

This repository includes a Helm chart under `./helm/heliotrapi`.

### Config support

The service supports configuration from one of these sources:

- `CONFIG_PATH` environment variable
- mounted config file at `/etc/config/config.yaml`
- local `config.yaml` file in the current working directory

In Kubernetes, the Helm chart mounts `config.yaml` from a `ConfigMap` and sets:

```yaml
env:
  - name: CONFIG_PATH
    value: "/etc/config/config.yaml"
```

### RabbitMQ config

The Helm values now expose RabbitMQ settings in the same shape as the app expects:

```yaml
config:
  rabbitmq:
    enabled: true
    host: ixx-analysis.diamond.ac.uk
    username: guest
    password: guest
    port: 61613
    destinations:
      - "/topic/public.worker.event"
      - "/topic/gda.messages.scan"
      - "/topic/gda.messages.processing"
      - "/topic/public.analysis.trigger"
```

## Helm usage

1. Build and push your Docker image

```bash
podman build -t ghcr.io/diamondlightsource/heliotrapi:latest .
podman push ghcr.io/diamondlightsource/heliotrapi:latest
```

2. Render the chart

```bash
helm template heliotrapi ./helm/heliotrapi
```

3. Dry-run validation

```bash
helm template heliotrapi ./helm/heliotrapi | kubectl apply --dry-run=client -f -
```

4. Install the chart

```bash
helm install heliotrapi ./helm/heliotrapi
```

5. Verify the deployment

```bash
kubectl get pods
kubectl get svc
```

6. Test the API

```bash
kubectl port-forward svc/heliotrapi 8000:8000
```

Then open:

```text
http://localhost:8000/
```

## Example Kubernetes Deployment

Go to the i15-services repo on gitlab.diamond.ac.uk to see an example of how to set it up
