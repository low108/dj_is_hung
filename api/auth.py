"""Who is calling: a Firebase ID token in `Authorization: Bearer <token>`, verified to a user id.

Locally the Firebase Auth emulator issues the tokens (FIREBASE_AUTH_EMULATOR_HOST makes firebase-admin
accept them); on Google Cloud they come from Firebase Auth. Tests pass their own verifier.
"""
from __future__ import annotations

import functools
import os
from collections.abc import Callable

from fastapi import HTTPException, Request

TokenVerifier = Callable[[str], str]  # token -> uid; raises on a bad token


@functools.cache
def firebase_verifier() -> TokenVerifier:
    import firebase_admin
    from firebase_admin import auth

    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "demo-dj-is-hung")
    try:
        app = firebase_admin.get_app()
    except ValueError:
        app = firebase_admin.initialize_app(options={"projectId": project})

    def verify(token: str) -> str:
        return auth.verify_id_token(token, app=app)["uid"]

    return verify


def current_user(request: Request) -> str:
    """FastAPI dependency: the signed-in user's id, or 401."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "sign in first")
    try:
        return request.app.state.verify_token(token)
    except Exception as e:
        raise HTTPException(401, "your sign-in has expired; sign in again") from e
