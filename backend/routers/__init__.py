"""API routers for the cert-layoff search app.

Each submodule exposes a module-level ``router = APIRouter()``. ``backend.main``
imports and includes them. All routes live under ``/api`` and require a valid
magic-link token via ``backend.auth.require_user``.
"""
