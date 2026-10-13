"""Google's verifier checks signature, audience, issuer, and token expiry."""

from asyncio import to_thread
from functools import partial

import requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token


def _verify(credential: str, client_id: str) -> dict:
    # Certificate retrieval is bounded and runs off the event loop.
    with requests.Session() as session:
        transport = partial(Request(session=session), timeout=10)
        return id_token.verify_oauth2_token(credential, transport, client_id)


async def verify_google_credential(credential: str, client_id: str) -> dict:
    return await to_thread(_verify, credential, client_id)
