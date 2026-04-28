from fastapi import FastAPI, Request

from fastapi_oneid import OneIDAuthPayload, create_api_router, create_web_router

app = FastAPI(title="FastAPI OneID Example")


async def oneid_handler(payload: OneIDAuthPayload, request: Request) -> dict:
    return {
        "token": "replace-with-project-token",
        "user": {
            "pin": payload.user.pin,
            "full_name": payload.user.full_name,
            "valid": payload.user.valid,
        },
    }


app.include_router(create_web_router(handler=oneid_handler))
app.include_router(create_api_router(handler=oneid_handler))
