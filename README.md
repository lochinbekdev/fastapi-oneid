# fastapi-oneid

`fastapi-oneid` is a reusable FastAPI package for integrating with Uzbekistan OneID SSO using the official OneID OAuth2 flow. The package handles authorization URL generation, state protection, token exchange, user-info lookup, and optional logout, while your application remains responsible for local user mapping and JWT or session issuance.

## Installation

```bash
pip install fastapi-oneid
```

For local development:

```bash
pip install -e .[dev]
```

## Environment Settings

The package reads configuration from environment variables.

| Variable | Required | Description |
| --- | --- | --- |
| `ONE_ID_SSO_URL` | Yes | OneID authorization and token endpoint, usually `https://sso.egov.uz/sso/oauth/Authorization.do` |
| `ONE_ID_CLIENT_ID` | Yes | OneID client identifier |
| `ONE_ID_CLIENT_SECRET` | Yes | OneID client secret |
| `ONE_ID_SCOPE` | Yes | OneID scope provided by the operator |
| `ONE_ID_ALLOWED_REDIRECT_URIS` | Yes | JSON array or comma-separated list of allowed redirect URIs |
| `ONE_ID_DEFAULT_REDIRECT_URI` | Yes | Default redirect URI, must be included in the allow-list |
| `ONE_ID_TIMEOUT` | No | Upstream request timeout in seconds. Default: `5.0` |
| `ONE_ID_DEBUG` | No | If `true`, raw OneID payloads may be returned when no handler is configured. Default: `false` |

Example `.env`:

```dotenv
ONE_ID_SSO_URL=https://sso.egov.uz/sso/oauth/Authorization.do
ONE_ID_CLIENT_ID=myportal
ONE_ID_CLIENT_SECRET=super-secret
ONE_ID_SCOPE=myportal
ONE_ID_ALLOWED_REDIRECT_URIS=["https://backend.example.com/one-id/access","https://frontend.example.com/auth/oneid/callback"]
ONE_ID_DEFAULT_REDIRECT_URI=https://backend.example.com/one-id/access
ONE_ID_TIMEOUT=5.0
ONE_ID_DEBUG=false
```

## Official OneID Grant Values

The package uses the OneID values required by the official technological guide:

- Authorization request: `response_type=one_code`
- Token exchange: `grant_type=one_authorization_code`
- User info request: `grant_type=one_access_token_identify`
- Logout request: `grant_type=one_log_out`

## Redirect URI Whitelist

OneID redirect URIs are not accepted freely from the client. Every requested redirect URI must:

- be present in `ONE_ID_ALLOWED_REDIRECT_URIS`
- be an absolute HTTP(S) URL
- not use `localhost`, `127.0.0.1`, `::1`, or other loopback hosts

The package also binds each generated OAuth `state` to the selected redirect URI. During callback and token exchange, the same redirect URI must be used again or the request is rejected.

## Quick Start

```python
from fastapi import FastAPI, Request
from fastapi_oneid import OneIDAuthPayload, create_api_router, create_web_router

app = FastAPI(title="My OneID Integration")


async def auth_handler(payload: OneIDAuthPayload, request: Request) -> dict:
    # 1. Find or create your local user
    # 2. Issue your own JWT or session
    # 3. Return the response expected by your frontend
    return {
        "token": "project-jwt",
        "user": {
            "pin": payload.user.pin,
            "full_name": payload.user.full_name,
        },
    }


app.include_router(create_web_router(handler=auth_handler))
app.include_router(create_api_router(handler=auth_handler))
```

## Web Flow Example

Default web endpoints:

- `GET /one-id/login`
- `GET /one-id/access`

Flow:

1. User opens `/one-id/login`
2. Package validates the redirect URI and generates a single-use `state`
3. User is redirected to OneID
4. OneID redirects back to `/one-id/access?code=...&state=...`
5. Package verifies `state`, exchanges `code` for `access_token`, fetches user info, and passes the result to your handler

Example login URL:

```text
GET /one-id/login
```

Optional alternative redirect URI from the whitelist:

```text
GET /one-id/login?redirect_uri=https://frontend.example.com/auth/oneid/callback
```

## API Flow Example

Default API endpoints:

- `GET /api/one-id/url`
- `POST /api/one-id/url` (compatibility alias)
- `GET /api/one-id/access`
- `POST /api/one-id/token`
- `POST /api/one-id/logout`

Flow:

1. Frontend requests `/api/one-id/url`
2. Backend returns a OneID authorization URL with a generated `state`
3. Frontend redirects the user to OneID
4. OneID redirects to the registered callback URI with `code` and `state`
5. Frontend sends `code` and `state` to `/api/one-id/token`
6. Package verifies the stored `state`, resolves the OneID user, and calls your handler

Requesting the authorization URL:

```bash
curl "https://backend.example.com/api/one-id/url?redirect_uri=https://frontend.example.com/auth/oneid/callback"
```

Exchanging the callback code:

```bash
curl -X POST "https://backend.example.com/api/one-id/token" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "oneid-returned-code",
    "state": "oneid-returned-state",
    "redirect_uri": "https://frontend.example.com/auth/oneid/callback"
  }'
```

The optional `redirect_uri` on `/api/one-id/token` is validated against the state-bound redirect URI. If it does not match, the request is rejected.

## Handler Example

Your handler receives a typed `OneIDAuthPayload` and the FastAPI `Request`.

```python
from fastapi import Request
from fastapi_oneid import OneIDAuthPayload


async def auth_handler(payload: OneIDAuthPayload, request: Request) -> dict:
    user = payload.user

    return {
        "token": "project-jwt",
        "profile": {
            "pin": user.pin,
            "full_name": user.full_name,
            "is_validated": user.valid,
        },
    }
```

The package does not create users, issue JWTs, or manage sessions automatically.

## Logout Example

Low-level client usage:

```python
from fastapi_oneid import OneIDClient, OneIDSettings

client = OneIDClient(settings=OneIDSettings())
logout_response = await client.logout("access-token")
```

Router usage:

```bash
curl -X POST "https://backend.example.com/api/one-id/logout" \
  -H "Content-Type: application/json" \
  -d '{"access_token": "oneid-access-token"}'
```

## Production Security Notes

- `state` is generated per login request and verified during callback and token exchange.
- Raw token payloads are not returned by default. They are only exposed when `ONE_ID_DEBUG=true` and no handler is configured.
- `client_secret` and `access_token` should never be logged by your application.
- Package-level timeout defaults to 5 seconds to match the official operational guideline.
- Configure application-level rate limiting or gateway protection in production.
- The OneID guide recommends not exceeding `300 requests per minute`.
- Use HTTPS public domains for registered redirect URIs. Do not rely on `localhost`.

## Testing

Run the unit tests:

```bash
python -m pytest -v
```

The tests mock OneID responses and cover the official grant types, redirect URI whitelist validation, state verification, typed user parsing, logout, and safe default handler behavior.

## License

MIT
