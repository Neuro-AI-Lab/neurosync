"""Minimal repro for the pinned-fastapi/starlette dependency-override
regression that breaks `tests/conftest.py`'s `client` fixture.

No DB / network required — isolates the exact pattern used by
`tests/conftest.py:138` (`app.dependency_overrides[get_session] = lambda: _yield(db_session)`)
against a bare FastAPI app + async-generator dependency, on the repo's own
pinned `fastapi==0.136.3` / `starlette==1.2.1` (see `apps/api/uv.lock`).

Filed against: BUG (qa, this pass) — "apps/api pytest client fixture
AttributeError: 'async_generator' object has no attribute '<attr>'" across
~44 tests in test_auth_login.py / test_auth_register.py / test_clinician.py /
test_intake_flow.py / test_stt_endpoint.py / test_websocket_chat.py whenever
the suite is actually run with `uv sync` deps installed (previously masked
by "apps/api/.venv lacks pydantic").
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


class _Resource:
    def __init__(self, tag: str) -> None:
        self.tag = tag


async def _get_resource() -> _Resource:  # pragma: no cover - real dependency stub
    raise RuntimeError("not overridden")


async def _yield(value: _Resource):
    yield value


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/probe")
    async def probe(res: Annotated[_Resource, Depends(_get_resource)]) -> dict:
        return {"tag": res.tag}

    return app


def test_conftest_style_override_is_broken_on_pinned_fastapi():
    """Reproduces `tests/conftest.py:138`'s exact override pattern.

    `lambda: _yield(value)` is a plain callable that returns an
    already-constructed async-generator *instance* — it is NOT itself an
    async-generator *function*, so FastAPI's dependency resolution
    (`fastapi.dependencies.utils.is_async_gen_callable`, which inspects the
    override *callable*, not its return value) does not special-case it.
    The raw async-generator object is injected as the dependency VALUE
    instead of being iterated for its yielded item.
    """
    app = _build_app()
    resource = _Resource(tag="expected")
    app.dependency_overrides[_get_resource] = lambda: _yield(resource)

    # `raise_server_exceptions=False` mirrors what a real deployed server
    # would do (500 response) rather than TestClient's default of
    # re-raising in-process — the underlying defect is identical either
    # way (`tests/conftest.py`'s own `client` fixture hits this same
    # AttributeError verbatim when pytest calls the actual test suite).
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/probe")

    assert resp.status_code == 500, (
        f"expected the known-broken 500 (AttributeError on async_generator), "
        f"got {resp.status_code}: {resp.text} — if this now passes, the "
        f"fastapi/starlette pin or the override pattern has changed; re-verify "
        f"tests/conftest.py's `client` fixture directly and update/close this bug."
    )


def test_correct_override_pattern_works():
    """The fix: override with the async-generator FUNCTION itself (optionally
    via functools.partial), not a lambda wrapping an already-invoked call —
    this is what makes FastAPI recognize and iterate it as a generator dep.
    """
    import functools

    app = _build_app()
    resource = _Resource(tag="expected")
    app.dependency_overrides[_get_resource] = functools.partial(_yield, resource)

    client = TestClient(app)
    resp = client.get("/probe")

    assert resp.status_code == 200
    assert resp.json() == {"tag": "expected"}
