from __future__ import annotations

import os
from functools import lru_cache

import firebase_admin
from firebase_admin import firestore as admin_firestore
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore


@lru_cache(maxsize=1)
def get_firestore_client() -> firestore.Client:
    """Usa credenciales anónimas solo cuando apunta al emulador local."""
    project_id = os.getenv("GCLOUD_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if os.getenv("FIRESTORE_EMULATOR_HOST"):
        return firestore.Client(
            project=project_id or "demo-smart-tanks",
            credentials=AnonymousCredentials(),
        )

    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app()
    return admin_firestore.client()
