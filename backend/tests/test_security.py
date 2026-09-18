"""Task 2.4: the limits, the allowlist, and the containment guards.

One section per PLAN.md defect, so a failure names the thing that regressed.
The rate limiter is off in the rest of the suite (``SECURITY_RATE_LIMIT_ENABLED``
is pinned false in ``conftest.TEST_ENV``); the tests here that want it switch it
on for themselves through :func:`enabled_limiter`, which also drops the cached
policy and the bucket state on the way in *and* on the way out, so no bucket
survives into another test.
"""

from __future__ import annotations

import io
import os

import pytest
from fastapi import UploadFile

from resumetailor.core.errors import (
    HTTP_MAPPED_ERRORS,
    LLMUnavailableError,
    PDFExtractError,
    RateLimitedError,
    RenderError,
    RequestTooLargeError,
    error_response,
)
from resumetailor.core.security import (
    MAX_CHAT_MESSAGE_CHARS,
    RATE_LIMITED_PATHS,
    TokenBucketLimiter,
    client_key,
    read_upload_capped,
    reset_security_caches,
    resolve_within,
    retry_after_seconds,
    subprocess_env,
)


@pytest.fixture
def clean_security_caches():
    """Drop the cached policy and limiter around a test that changes either."""
    reset_security_caches()
    try:
        yield
    finally:
        reset_security_caches()


@pytest.fixture
def enabled_limiter(monkeypatch, clean_security_caches):
    """Turn the limiter on with a tiny bucket that does not refill mid-test."""
    monkeypatch.setenv("SECURITY_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("SECURITY_RATE_LIMIT_BURST", "2")
    monkeypatch.setenv("SECURITY_RATE_LIMIT_PER_MINUTE", "1")
    reset_security_caches()


# ── D-25: path containment ───────────────────────────────────────────────────


def test_resolve_within_accepts_a_plain_filename(tmp_path):
    assert resolve_within(tmp_path, "7.pdf") == (tmp_path / "7.pdf").resolve()


@pytest.mark.parametrize(
    "hostile",
    [
        "../outside.pdf",
        "../../etc/passwd",
        "a/../../outside.pdf",
        "/etc/passwd",
        "",
        ".",
    ],
)
def test_resolve_within_refuses_anything_that_escapes(tmp_path, hostile):
    assert resolve_within(tmp_path / "pdfs", hostile) is None


def test_resolve_within_allows_a_nested_path_inside_the_root(tmp_path):
    resolved = resolve_within(tmp_path, "nested/7.pdf")
    assert resolved == (tmp_path / "nested" / "7.pdf").resolve()


@pytest.mark.anyio
async def test_pdf_route_404s_on_a_traversing_stored_path(client, db_path, pdfs_dir):
    """The guard, through the route, on a row poisoned the way D-25 describes.

    The column is server-generated today, so this writes the hostile value
    directly. A 404 rather than a 403: a 403 would confirm both that the file
    exists and that a check refused it.
    """
    from pathlib import Path

    from resumetailor.db.repositories import create_resume, update_resume

    outside = Path(pdfs_dir).parent / "outside.pdf"
    outside.write_bytes(b"%PDF-1.4 not yours")

    row = create_resume(db_path, "n", "jd", "cv:\n  name: T")
    update_resume(db_path, row.id, pdf_path="../outside.pdf")

    response = await client.get(f"/api/resumes/{row.id}/pdf")
    assert response.status_code == 404
    assert outside.exists(), "the guard must not have served it either"


@pytest.mark.anyio
async def test_delete_does_not_unlink_outside_the_pdf_directory(
    client, db_path, pdfs_dir
):
    from pathlib import Path

    from resumetailor.db.repositories import create_resume, update_resume

    outside = Path(pdfs_dir).parent / "outside.pdf"
    outside.write_bytes(b"%PDF-1.4 not yours")

    row = create_resume(db_path, "n", "jd", "cv:\n  name: T")
    update_resume(db_path, row.id, pdf_path="../outside.pdf")

    response = await client.delete(f"/api/resumes/{row.id}")
    assert response.status_code == 204
    assert outside.exists(), "delete unlinked a file outside PDFS_DIR"


# ── D-49: the subprocess environment allowlist ───────────────────────────────


def test_subprocess_env_drops_the_provider_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-a-real-key-for-a-test")
    monkeypatch.setenv("SOME_OTHER_SECRET", "also-not-inherited")
    env = subprocess_env()
    assert "OPENAI_API_KEY" not in env
    assert "SOME_OTHER_SECRET" not in env


def test_subprocess_env_keeps_what_rendercv_needs(monkeypatch):
    monkeypatch.setenv("PATH", "/venv/bin:/usr/bin")
    monkeypatch.setenv("HOME", "/home/app")
    env = subprocess_env()
    assert env["PATH"] == "/venv/bin:/usr/bin"
    assert env["HOME"] == "/home/app"
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONNOUSERSITE"] == "1"


def test_subprocess_env_never_has_an_empty_path(monkeypatch):
    monkeypatch.delenv("PATH", raising=False)
    assert subprocess_env()["PATH"] == os.defpath


def test_subprocess_env_drops_our_own_pythonpath(monkeypatch):
    """rendercv has no business importing from `resumetailor`'s src tree."""
    monkeypatch.setenv("PYTHONPATH", "/app/backend/src")
    assert "PYTHONPATH" not in subprocess_env()


@pytest.mark.anyio
async def test_runner_passes_the_scrubbed_env_to_the_child(monkeypatch):
    """The wiring, not just the helper: `env=` reaches the subprocess call."""
    from resumetailor.rendering import runner

    captured: dict[str, dict[str, str]] = {}

    async def fake_exec(*_args, **kwargs):
        captured["env"] = kwargs["env"]
        msg = "not actually rendering"
        raise RuntimeError(msg)

    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-a-real-key-for-a-test")
    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", fake_exec)

    with pytest.raises(RuntimeError):
        await runner.RenderCVAdapter().render("cv:\n  name: T")

    assert "OPENAI_API_KEY" not in captured["env"]
    assert "PATH" in captured["env"]


# ── D-47: input length bounds ────────────────────────────────────────────────


@pytest.mark.anyio
async def test_oversized_chat_message_is_rejected_before_the_provider(client, sim):
    response = await client.post(
        "/api/chat/stream", json={"message": "x" * (MAX_CHAT_MESSAGE_CHARS + 1)}
    )
    assert response.status_code == 422
    assert sim.sim_llm.stream_call_count == 0


@pytest.mark.anyio
async def test_message_at_the_bound_is_accepted(client, sim):
    response = await client.post(
        "/api/chat/stream", json={"message": "x" * MAX_CHAT_MESSAGE_CHARS}
    )
    assert response.status_code == 200


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        (
            "POST",
            "/api/evaluate/stream",
            {"yaml_content": "x", "job_description": "OVER"},
        ),
        (
            "POST",
            "/api/evaluate/stream",
            {"yaml_content": "OVER", "job_description": "x"},
        ),
        ("POST", "/api/resumes/stream", {"job_description": "OVER"}),
        ("PUT", "/api/master-resume", {"yaml_content": "OVER"}),
        ("PUT", "/api/system-prompt", {"content": "OVER"}),
    ],
)
async def test_every_bare_str_request_field_now_has_a_bound(client, method, path, body):
    """One case per field named in D-47. `OVER` stands in for a 200 KB value."""
    oversized = {k: ("x" * 200_000 if v == "OVER" else v) for k, v in body.items()}
    response = await client.request(method, path, json=oversized)
    assert response.status_code == 422


# ── D-47: the request body cap ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_declared_content_length_over_the_cap_is_refused(
    client, monkeypatch, clean_security_caches
):
    monkeypatch.setenv("SECURITY_MAX_JSON_BODY_BYTES", "512")
    reset_security_caches()
    response = await client.post(
        "/api/evaluate/stream",
        json={"yaml_content": "x" * 4096, "job_description": "y"},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "REQUEST_TOO_LARGE"


@pytest.mark.anyio
async def test_body_cap_holds_without_a_content_length(
    client, monkeypatch, clean_security_caches
):
    """A chunked body has no Content-Length, so the running total is the guard."""
    monkeypatch.setenv("SECURITY_MAX_JSON_BODY_BYTES", "512")
    reset_security_caches()

    async def chunks():
        yield b'{"message": "'
        for _ in range(8):
            yield b"x" * 256
        yield b'"}'

    response = await client.post("/api/chat/stream", content=chunks())
    assert response.status_code == 413
    assert response.json()["code"] == "REQUEST_TOO_LARGE"


@pytest.mark.anyio
async def test_a_normal_body_is_untouched(client, monkeypatch, clean_security_caches):
    monkeypatch.setenv("SECURITY_MAX_JSON_BODY_BYTES", "512")
    reset_security_caches()
    response = await client.post("/api/chat/stream", json={"message": "Hi"})
    assert response.status_code == 200


# ── D-48: the streaming upload cap ───────────────────────────────────────────


@pytest.mark.anyio
async def test_read_upload_capped_aborts_before_buffering_everything():
    upload = UploadFile(file=io.BytesIO(b"z" * 4096), filename="big.pdf")
    with pytest.raises(RequestTooLargeError) as raised:
        await read_upload_capped(upload, max_bytes=1024, chunk_size=256)
    # The detail must name the cap; the client never sees it (D-53).
    assert "1024" in str(raised.value)
    assert raised.value.status_code == 413


@pytest.mark.anyio
async def test_read_upload_capped_returns_a_file_at_the_bound():
    payload = b"z" * 1024
    upload = UploadFile(file=io.BytesIO(payload), filename="ok.pdf")
    assert await read_upload_capped(upload, max_bytes=1024, chunk_size=256) == payload


@pytest.mark.anyio
async def test_the_upload_cap_surfaces_as_a_413_through_the_route(
    client, sim, monkeypatch
):
    """The D-48 guard proper, past the body-size middleware.

    Worth its own test because of where the raise happens: FastAPI turns any
    exception raised while *parsing* a body into a 400 with its own envelope.
    This one is raised in the endpoint function, which is outside that `try`,
    so it must come back as this application's 413.
    """
    from resumetailor.core import security

    monkeypatch.setattr(security, "MAX_PDF_UPLOAD_BYTES", 256)
    response = await client.post(
        "/api/master-resume/import",
        files={
            "file": ("big.pdf", io.BytesIO(b"%PDF" + b"z" * 4096), "application/pdf")
        },
    )
    assert response.status_code == 413
    assert response.json()["code"] == "REQUEST_TOO_LARGE"
    assert sim.sim_pdf_extract.call_count == 0


@pytest.mark.anyio
async def test_import_refuses_an_oversized_upload(
    client, sim, monkeypatch, clean_security_caches
):
    monkeypatch.setenv("SECURITY_MAX_UPLOAD_BODY_BYTES", "2048")
    reset_security_caches()
    response = await client.post(
        "/api/master-resume/import",
        files={
            "file": ("big.pdf", io.BytesIO(b"%PDF" + b"z" * 8192), "application/pdf")
        },
    )
    assert response.status_code == 413
    assert response.json()["code"] == "REQUEST_TOO_LARGE"
    assert sim.sim_pdf_extract.call_count == 0


# ── Rate limiting (D-28's cost half) ─────────────────────────────────────────


def test_token_bucket_allows_the_burst_then_refuses():
    limiter = TokenBucketLimiter(capacity=3.0, refill_per_second=0.1)
    assert [limiter.check("a", now=100.0) for _ in range(3)] == [0.0, 0.0, 0.0]
    assert limiter.check("a", now=100.0) == pytest.approx(10.0)


def test_token_bucket_refills_over_time():
    limiter = TokenBucketLimiter(capacity=1.0, refill_per_second=1.0)
    assert limiter.check("a", now=0.0) == 0.0
    assert limiter.check("a", now=0.5) > 0.0
    assert limiter.check("a", now=1.0) == 0.0


def test_token_bucket_meters_each_client_separately():
    limiter = TokenBucketLimiter(capacity=1.0, refill_per_second=0.1)
    assert limiter.check("a", now=0.0) == 0.0
    assert limiter.check("b", now=0.0) == 0.0
    assert limiter.check("a", now=0.0) > 0.0


def test_token_bucket_store_is_bounded():
    """The store is keyed on an attacker-controlled value; it must not grow."""
    limiter = TokenBucketLimiter(capacity=1.0, refill_per_second=1.0)
    for i in range(5_000):
        limiter.check(f"client-{i}", now=float(i))
    assert len(limiter._buckets) <= 1024


def test_retry_after_never_rounds_down_to_zero():
    assert retry_after_seconds(0.01) == 1
    assert retry_after_seconds(9.2) == 10


def test_client_key_falls_back_when_there_is_no_peer():
    assert client_key(None) == "unknown"
    assert client_key(("10.0.0.4", 51234)) == "10.0.0.4"


@pytest.mark.anyio
async def test_llm_endpoint_is_rate_limited(client, enabled_limiter):
    first = await client.post("/api/chat/stream", json={"message": "Hi"})
    second = await client.post("/api/chat/stream", json={"message": "Hi"})
    third = await client.post("/api/chat/stream", json={"message": "Hi"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json() == {
        "error": RateLimitedError.client_message,
        "code": "RATE_LIMITED",
    }
    assert int(third.headers["retry-after"]) >= 1


@pytest.mark.anyio
async def test_a_rate_limited_response_still_carries_a_request_id(
    client, enabled_limiter
):
    """Proves the middleware order: the limiter runs inside request context."""
    for _ in range(3):
        response = await client.post("/api/chat/stream", json={"message": "Hi"})
    assert response.status_code == 429
    assert response.headers["x-request-id"]


@pytest.mark.anyio
async def test_the_limited_request_never_reaches_the_provider(
    client, sim, enabled_limiter
):
    for _ in range(4):
        await client.post(
            "/api/evaluate/stream",
            json={
                "yaml_content": "cv:\n  name: T",
                "job_description": "jd",
            },
        )
    assert sim.sim_llm.complete_call_count == 2


@pytest.mark.anyio
async def test_reads_are_not_rate_limited(client, enabled_limiter):
    for _ in range(10):
        response = await client.get("/api/health")
        assert response.status_code == 200


@pytest.mark.anyio
async def test_the_limiter_can_be_turned_off(
    client, monkeypatch, clean_security_caches
):
    monkeypatch.setenv("SECURITY_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("SECURITY_RATE_LIMIT_BURST", "1")
    reset_security_caches()
    for _ in range(5):
        response = await client.post("/api/chat/stream", json={"message": "Hi"})
        assert response.status_code == 200


def test_every_llm_endpoint_is_in_the_limited_set():
    """The four paths D-28 names. A new provider-calling route must join them."""
    expected = {
        "/api/chat/stream",
        "/api/resumes/stream",
        "/api/evaluate/stream",
        "/api/master-resume/import",
    }
    assert expected == RATE_LIMITED_PATHS


# ── D-53: opaque client errors, full detail in the log ───────────────────────


def test_error_response_returns_the_generic_message_not_the_detail():
    leak = "/app/backend/.venv/lib/typst.py:118 Traceback ... sk-leaked"
    payload = error_response(RenderError(leak))
    body = payload.body.decode()
    assert leak not in body
    assert RenderError.client_message in body
    assert '"code":"RENDER_FAILED"' in body.replace(" ", "")


def test_the_detail_is_still_available_to_the_operator():
    leak = "rendercv failed (exit 1): /app/tmp/abc/resume.typ"
    error = RenderError(leak)
    assert error.detail == leak
    assert str(error) == leak, "str(exc) stays the operator's view, for tracebacks"


@pytest.mark.parametrize("error_type", HTTP_MAPPED_ERRORS)
def test_every_http_mapped_error_has_its_own_client_message(error_type):
    from resumetailor.core.errors import BackendError

    assert error_type.client_message != BackendError.client_message
    assert error_type.code != BackendError.code


def test_request_too_large_is_mapped_and_rate_limited_is_not():
    """RateLimitedError is built by middleware, outside the handler stack."""
    assert RequestTooLargeError in HTTP_MAPPED_ERRORS
    assert RateLimitedError not in HTTP_MAPPED_ERRORS


@pytest.mark.anyio
async def test_a_mapped_error_reaches_the_client_opaquely(client, sim, caplog):
    leak = "Cannot open PDF: /app/pdfs/secret.pdf is not a PDF"
    sim.sim_pdf_extract.set_error(PDFExtractError(leak))

    with caplog.at_level("ERROR"):
        response = await client.post(
            "/api/master-resume/import",
            files={"file": ("r.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        )

    assert response.status_code == 422
    assert response.json() == {
        "error": PDFExtractError.client_message,
        "code": "PDF_EXTRACT_FAILED",
    }
    assert leak not in response.text
    assert any(
        getattr(record, "error_detail", None) == leak for record in caplog.records
    ), "the detail must be logged even though the client never sees it"


@pytest.mark.anyio
async def test_the_preview_route_does_not_leak_render_output(client, sim):
    leak = "rendercv failed (exit 1): Typst error at /app/backend/.venv/..."
    await client.put("/api/master-resume", json={"yaml_content": "cv:\n  name: T"})
    sim.sim_pdf_render.set_error(RenderError(leak))
    response = await client.get("/api/master-resume/preview")
    assert response.status_code == 422
    assert leak not in response.text


@pytest.mark.anyio
async def test_provider_exception_text_does_not_reach_the_client(client, sim, caplog):
    """D-53 on the streaming path, closed by task 2.5 for the two routes it owns.

    The marker this test carried (``xfail(strict=True)``) is gone: both SSE
    routes below now frame ``exc.client_message`` and log the detail, exactly
    as ``error_response`` does for a non-streaming route.
    ``test_chat_stream_still_leaks_provider_exception_text`` below is the same
    assertion against the third streaming route, which is still open.
    """
    leak = "litellm.APIError: POST https://api.openai.com/v1/chat key=sk-xyz"
    sim.sim_llm.set_complete_error(LLMUnavailableError(leak))

    with caplog.at_level("ERROR"):
        response = await client.post(
            "/api/evaluate/stream",
            json={"yaml_content": "cv:\n  name: T", "job_description": "jd"},
        )

    assert leak not in response.text
    assert LLMUnavailableError.client_message in response.text
    assert '"code": "LLM_UNAVAILABLE"' in response.text
    assert any(
        getattr(record, "error_detail", None) == leak for record in caplog.records
    ), "the detail must be logged even though the client never sees it"


@pytest.mark.anyio
async def test_generation_stream_does_not_leak_provider_exception_text(
    client, sim, caplog
):
    """The same guarantee on the generation stream, which errors mid-pipeline."""
    leak = "litellm.APIError: POST https://api.openai.com/v1/chat key=sk-xyz"
    await client.put("/api/master-resume", json={"yaml_content": "cv:\n  name: T"})
    sim.sim_llm.set_complete_error(LLMUnavailableError(leak))

    with caplog.at_level("ERROR"):
        response = await client.post(
            "/api/resumes/stream", json={"job_description": "jd"}
        )

    assert leak not in response.text
    assert LLMUnavailableError.client_message in response.text
    assert '"code": "LLM_UNAVAILABLE"' in response.text
    assert any(
        getattr(record, "error_detail", None) == leak for record in caplog.records
    ), "the detail must be logged even though the client never sees it"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "D-53's remaining residual. `api/routers/chat.py` is the third "
        "streaming route and was outside both task 2.4's and task 2.5's file "
        "ownership, so it still puts str(exc) in the SSE error frame. Whoever "
        "owns that file next replaces it with exc.client_message, at which "
        "point this passes and xfail_strict fails the build so the marker gets "
        "removed."
    ),
)
@pytest.mark.anyio
async def test_chat_stream_still_leaks_provider_exception_text(client, sim):
    leak = "litellm.APIError: POST https://api.openai.com/v1/chat key=sk-xyz"
    sim.sim_llm.set_stream_error(LLMUnavailableError(leak))
    response = await client.post("/api/chat/stream", json={"message": "hi"})
    assert leak not in response.text
