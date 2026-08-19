"""Punto de entrada descubierto por Cloud Functions for Firebase."""

from firebase_functions import https_fn, options

from src.http_app import app


@https_fn.on_request(
    region="us-east1",
    memory=options.MemoryOption.MB_256,
    timeout_sec=60,
    max_instances=3,
)
def api(request: https_fn.Request) -> https_fn.Response:
    """Expone la aplicación Flask como una única API HTTPS versionada."""
    with app.request_context(request.environ):
        return app.full_dispatch_request()

