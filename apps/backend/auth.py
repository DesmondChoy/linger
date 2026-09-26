"""Sign-in routes and request identity.

Every account-scoped route requires a bearer login token issued by
`/api/auth/signup` or `/api/auth/login`; the account comes from that token,
never from request content.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

from src.linger.services.memory import AccountContext

from .accounts import AccountStore, UsernameTakenError
from .config import REPO_ROOT

account_store = AccountStore(REPO_ROOT / "data" / "accounts.sqlite3")
router = APIRouter(prefix="/api/auth")
_bearer = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=6, max_length=200)

    @field_validator("username")
    @classmethod
    def _case_insensitive(cls, username: str) -> str:
        return username.lower()


class SignedIn(BaseModel):
    username: str
    token: str


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


def account_id_for(username: str) -> str:
    return f"user:{username}"


def current_username(credentials: BearerCredentials) -> str:
    if credentials is None:
        raise _unauthorized("Sign in to continue.")
    username = account_store.username_for(credentials.credentials)
    if username is None:
        raise _unauthorized("Your sign-in has expired. Sign in again.")
    return username


def current_account(
    username: Annotated[str, Depends(current_username)],
) -> AccountContext:
    return AccountContext(account_id_for(username))


AccountDependency = Annotated[AccountContext, Depends(current_account)]


@router.post("/signup", status_code=201)
def sign_up(credentials: Credentials) -> SignedIn:
    try:
        token = account_store.create_account(credentials.username, credentials.password)
    except UsernameTakenError:
        raise HTTPException(status_code=409, detail="That username is taken.") from None
    return SignedIn(username=credentials.username, token=token)


@router.post("/login")
def log_in(credentials: Credentials) -> SignedIn:
    token = account_store.login(credentials.username, credentials.password)
    if token is None:
        raise _unauthorized("Wrong username or password.")
    return SignedIn(username=credentials.username, token=token)


@router.get("/me")
def who_am_i(username: Annotated[str, Depends(current_username)]) -> dict[str, str]:
    return {"username": username}


@router.post("/logout", status_code=204)
def log_out(credentials: BearerCredentials) -> None:
    if credentials is not None:
        account_store.logout(credentials.credentials)
