# infra-connectors

`infra-connectors` bundles asynchronous helpers that wrap the HTTP APIs exposed by Argo CD, Git providers that implement the GitHub API, and HashiCorp Vault. The utilities were extracted from the Backstage provisioning service so other projects can reuse the same integration layer.

## Features

- Async clients that validate responses and raise typed exceptions.
- High-level helpers for synchronising Argo CD applications, manipulating Git repository contents, and managing Vault secrets.
- Shared logging configuration built on Loguru for consistent observability across services.
- Minimal dependency footprint so the utilities stay framework agnostic.

## Installation

```bash
pip install horizon-infra-connectors
```

## Usage

```python
from horizon_infra_connectors import ArgoCD, Git, Vault

argo = ArgoCD(
    base_url="https://argo.example.com",
    api_key="token",
    application_set_timeout=30,
)

git = Git(
    base_url="https://api.bitbucket.org/2.0",
    token="token",
    username_or_email="kingjohnny@example.com or kingJohnny",
    workspace="workspace",
    repo_slug="repo",
)

vault = Vault(
    base_url="https://vault.example.com",
    token="token",
)
```

Bitbucket is the default Git provider. To target GitHub instead, supply the `provider` argument:

```python
from horizon_infra_connectors import Git

github = Git(
    base_url="https://api.github.com/repos/org/repo",
    token="github-token",
    provider="github",
)

bitbucket_server = Git(
    base_url="https://bitbucket.example.com",
    token="token",
    username_or_email="service-user",
    repo_slug="repo",
    project_key="OPS",
    bitbucket_server=True,
)

bitbucket_server_http_token = Git(
    base_url="https://bitbucket.example.com",
    token="http-access-token",
    repo_slug="repo",
    project_key="OPS",
    bitbucket_server=True,
    bitbucket_http_token=True,
)
# Bitbucket Server requires HTTP access tokens that belong to a user account
# for write operations; repository- or project-scoped tokens cannot edit files.

### Bitbucket Server curl example

To call the Bitbucket Server REST API directly, issue a `PUT` request to the
files endpoint with multipart form fields for the commit metadata and the file
contents. The snippet below mirrors what the client sends when creating or
updating a file:

```bash
curl \
  -H "Authorization: Bearer ${HTTP_ACCESS_TOKEN}" \
  -X PUT "https://bitbucket.example.com/rest/api/1.0/projects/OPS/repos/repo/files/path/to/file.txt" \
  -F message="Automated update" \
  -F branch=main \
  -F content=@/absolute/path/to/local/file.txt
```

* Replace `${HTTP_ACCESS_TOKEN}` with a Bitbucket Server HTTP access token that belongs to a user account. Tokens created at the repository or project level do not include user identity and will be rejected for file edits. To use Basic auth instead, pass `-u "user:token"` rather than the `Authorization` header.
* Update the project key, repository slug, and file path for your repository.
* Include the `branch` field when committing to a non-default branch.
* `content` can reference a local file; to provide inline content, pipe text via
  process substitution (for example, `-F "content=< <(printf 'hello')"`).

### GitHub usage example

```python
import asyncio
from horizon_infra_connectors import Git

async def main() -> None:
    github = Git(
        base_url="https://api.github.com/repos/org/repo",
        token="github-token",
        provider="github",
    )
    await github.async_init()
    readme_text = await github.get_file_content("README.md")
    print(readme_text.splitlines()[0])

asyncio.run(main())
```

Each service exposes an underlying API client when you need lower-level control:

```python
import asyncio
from horizon_infra_connectors.argocd import ArgoCDAPI

async def main() -> None:
    api = ArgoCDAPI(base_url="https://argo.example.com", api_key="token")
    app = await api.get_application("example")
    print(app["metadata"]["name"])

asyncio.run(main())
```

The package raises rich exceptions that inherit from `infra_connectors.errors.ExternalServiceError`, making it simple to map failures to HTTP responses or retry logic.

See the module docstrings for additional usage examples.
