"""Типові помилки при підміні обробників: обробник на fastapi.HTTPException, exc.errors() без кодування, input у відповіді."""
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

app = FastAPI()


class Signup(BaseModel):
    email: str
    password: str = Field(min_length=12)

    @field_validator("email")
    @classmethod
    def has_at(cls, value: str) -> str:
        if "@" not in value:
            raise ValueError("email без @")
        return value


@app.exception_handler(HTTPException)                      # fastapi.HTTPException — підклас starlette
async def http_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"problem": exc.detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse({"errors": exc.errors()}, status_code=422)   # без jsonable_encoder


@app.post("/signup")
def signup(body: Signup) -> dict:
    return {"ok": True}


@app.get("/items/{item_id}")
def item(item_id: int) -> dict:
    raise HTTPException(404, "Item not found")
