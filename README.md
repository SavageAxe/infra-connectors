# infra-connectors

`infra-connectors` bundles asynchronous helpers that wrap the HTTP APIs exposed by Argo CD, Git providers that implement the GitHub API, and HashiCorp Vault. The utilities are extracted from the backstage provisioning service so that other projects can reuse the same integration layer.

## Features

* Opinionated async clients that validate responses and raise rich exceptions.
* High level helpers for synchronising Argo CD applications, manipulating Git repository contents, and managing Vault secrets.
* Reusable FastAPI scaffolding that mirrors the Backstage provisioning service, including logging configuration with resource prefixes.
* Designed to be framework agnostic with minimal dependencies.

## Installation

```
pip install infra-connectors
```

## Usage

```python
from infra_connectors import ArgoCD, Git, Vault

argo = ArgoCD(base_url="https://argo.example.com", api_key="token", application_set_timeout=30)
git = Git(base_url="https://api.github.com/repos/org/repo", token="token")
vault = Vault(base_url="https://vault.example.com", token="token")
```

For services built with FastAPI you can reuse the application factory and logging helpers:

```python
from infra_connectors.fastapi import create_app, basicSettings, logger_config

app = create_app()

# Access the configured loguru logger
from loguru import logger
logger.info("Application boot complete")
```

Each service is split into an API client and a higher level service wrapper. When you
need direct access to the client or logger you can import them from the service module:

```python
from infra_connectors.argocd.service import ArgoCD

argo_logger = ArgoCD.get_logger()
argo_logger.info("Configuring ArgoCD service logging")
```

See the module docstrings for concrete usage examples.
