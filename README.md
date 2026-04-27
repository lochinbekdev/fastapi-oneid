# fastapi-oneid

`fastapi-oneid` is a self-developed OneID integration package for FastAPI applications. It gives you a clean, reusable way to start the OneID authorization flow, exchange the returned code for an access token, fetch the authenticated user profile, and hand the final login step back to your own application.

The package is designed for teams that want to integrate OneID quickly without rebuilding the HTTP flow for every project.

## What This Package Does

- Generates a OneID authorization URL
- Redirects users to the OneID login page
- Exchanges the returned `code` for a OneID access token
- Fetches user information from OneID using the access token
- Exposes ready-to-mount FastAPI routers for web and API flows
- Lets your application finish local authentication through a callback handler

## What This Package Does Not Do

- It does not create local users automatically
- It does not issue JWTs or sessions automatically
- It does not manage your database models
- It does not bypass OneID redirect URI restrictions

Your application remains responsible for mapping the OneID user to a local account and issuing your own access token or session.

## Requirements

- Python `3.11+`
- FastAPI `0.115+`
- OneID client credentials
- A callback URL registered in your OneID client configuration

## Installation

Install from PyPI:

```bash
pip install fastapi-oneid
```

For local development:

```bash
pip install -e .[dev]
```

For release tooling:

```bash
pip install -e .[release]
```

## Configuration

The package reads configuration from environment variables.

| Variable | Required | Description |
| --- | --- | --- |
| `ONE_ID_SSO_URL` | Yes | OneID authorization/token endpoint URL |
| `ONE_ID_CLIENT_ID` | Yes | Your OneID client identifier |
| `ONE_ID_CLIENT_SECRET` | Yes | Your OneID client secret |
| `ONE_ID_CLIENT_SCOPE` | No | Scope to send to OneID. Default: `test` |
| `ONE_ID_CLIENT_STATE` | No | State value to send to OneID. Default: `testState` |

Example `.env`:

```dotenv
ONE_ID_SSO_URL=https://sso.egov.uz/sso/oauth/Authorization.do
ONE_ID_CLIENT_ID=your-client-id
ONE_ID_CLIENT_SECRET=your-client-secret
ONE_ID_CLIENT_SCOPE=test
ONE_ID_CLIENT_STATE=testState
```

## Quick Start

Create a FastAPI app and mount the provided routers.

```python
from fastapi import FastAPI, Request
from fastapi_oneid import OneIDAuthPayload, create_api_router, create_web_router

app = FastAPI(title="My OneID Integration")


async def auth_handler(payload: OneIDAuthPayload, request: Request) -> dict:
    oneid_user = payload.user

    # 1. Find or create a local user
    # 2. Issue your own JWT or session
    # 3. Return your final login response

    return {
        "token": "your-project-jwt",
        "user": oneid_user,
        "oneid_token": payload.token,
    }


app.include_router(create_web_router(handler=auth_handler))
app.include_router(create_api_router(handler=auth_handler))
```

Run the app:

```bash
uvicorn main:app --reload
```

## Integration Modes

### 1. Web Flow

Use the built-in redirect flow when your backend receives the callback directly.

Endpoints:

- `GET /one-id/login`
- `GET /one-id/access`

Flow:

1. User opens `/one-id/login`
2. The package redirects the user to OneID
3. OneID redirects back to `/one-id/access?code=...`
4. The package exchanges the code and fetches the user
5. Your `auth_handler` decides how to log the user into your application

This is usually the simplest approach for server-rendered or backend-controlled login flows.

### 2. API Flow

Use the API flow when your frontend wants to control the browser redirect.

Endpoints:

- `GET /api/one-id/url`
- `POST /api/one-id/url`
- `POST /api/one-id/token`
- `GET /api/one-id/access`

Flow:

1. Frontend requests `/api/one-id/url`
2. Backend returns a OneID authorization URL
3. Frontend redirects the user to that URL
4. OneID redirects to the callback URL registered for your client
5. Frontend sends the returned `code` to `/api/one-id/token`
6. The package resolves the OneID user and calls your `auth_handler`

## Default Routes

By default, the package exposes the following endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/one-id/login` | Redirect user to OneID |
| `GET` | `/one-id/access` | Handle web callback and resolve user |
| `GET` | `/api/one-id/url` | Return authorization URL |
| `POST` | `/api/one-id/url` | Return authorization URL |
| `POST` | `/api/one-id/token` | Exchange code and resolve user |
| `GET` | `/api/one-id/access` | Return received callback code |

You can override the router prefix:

```python
app.include_router(create_web_router(prefix="/auth/oneid"))
app.include_router(create_api_router(prefix="/api/auth/oneid"))
```

## Handler Contract

Your handler receives a `OneIDAuthPayload` object and the current FastAPI `Request`.

```python
from fastapi import Request
from fastapi_oneid import OneIDAuthPayload


async def auth_handler(payload: OneIDAuthPayload, request: Request) -> dict:
    return {
        "token": "your-project-jwt",
        "user": payload.user,
    }
```

`OneIDAuthPayload` contains:

- `code`: the authorization code returned by OneID
- `redirect_url`: the callback URL used in the flow
- `token`: the raw token payload returned by OneID
- `user`: the raw user payload returned by OneID

Your handler may return:

- a JSON-serializable `dict`
- any FastAPI `Response`

## Programmatic Usage

If you want to call OneID without mounting routers, use the low-level client directly.

```python
from fastapi_oneid import OneIDClient, OneIDSettings

settings = OneIDSettings()
client = OneIDClient(settings=settings)

authorization_url = client.get_authorization_url("https://example.com/callback")
```

Available client methods:

- `get_authorization_url(redirect_url, scope=None, state=None)`
- `exchange_code(code, redirect_url)`
- `get_user_info(access_token, scope=None)`
- `resolve_auth_payload(code, redirect_url)`
- `get_user(code, redirect_url)`

## Example Project

A minimal runnable example is available in:

- `examples/basic_app/main.py`

Run it locally:

```bash
cp .env.example .env
set -a
source .env
set +a
uvicorn examples.basic_app.main:app --reload --port 8010
```

Then open:

- `http://127.0.0.1:8010/api/one-id/url`
- `http://127.0.0.1:8010/one-id/login`

## Common Problems

### `REDIRECT_URI_NOT_ALLOWED`

OneID rejects callback URLs that are not registered for your client.

To fix it:

1. Register your callback URL in OneID
2. Use the exact same callback URL in the login flow
3. If you use the API flow, send the same `redirect_url` again when calling `/api/one-id/token`

Example:

```bash
curl "http://127.0.0.1:8010/api/one-id/url?redirect_url=http://127.0.0.1:3000/callback"
```

Then:

```bash
curl -X POST "http://127.0.0.1:8010/api/one-id/token" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "oneid-returned-code",
    "redirect_url": "http://127.0.0.1:3000/callback"
  }'
```

### Missing Environment Variables

If startup fails with validation errors for `ONE_ID_SSO_URL`, `ONE_ID_CLIENT_ID`, or `ONE_ID_CLIENT_SECRET`, load your environment variables before starting the application.

### Localhost Callback Problems

If OneID does not allow `localhost` or `127.0.0.1` callbacks for your client, use a registered domain or a development tunnel and register that callback in OneID.

## Testing

Run the unit tests:

```bash
python -m pytest -v
```

The tests mock OneID responses. Real OneID credentials are not required for the test suite.

## Release to PyPI

Build the package:

```bash
python -m build --no-isolation
```

Validate package metadata:

```bash
python -m twine check dist/*
```

Upload to TestPyPI:

```bash
python -m twine upload --repository testpypi dist/*
```

Upload to PyPI:

```bash
python -m twine upload dist/*
```

Before publishing:

1. Update `version` in `pyproject.toml`
2. Run the test suite
3. Build and check the distribution
4. Upload to TestPyPI before uploading to PyPI

Recommended verification after upload:

```bash
python3 -m venv /tmp/fastapi-oneid-check
source /tmp/fastapi-oneid-check/bin/activate
pip install fastapi-oneid
python -c "import fastapi_oneid; print('install ok')"
```

## License

MIT
