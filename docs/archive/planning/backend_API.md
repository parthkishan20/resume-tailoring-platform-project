# Backend API Reference

Raw research for the three external libraries the FastAPI backend depends on:
**LiteLLM → OpenRouter**, **render-cv**, and **PyMuPDF**.

Each section documents: install, environment, the specific calls the backend makes,
parameters used, and errors to handle.

---

## 1. LiteLLM → OpenRouter

LiteLLM provides a unified async interface over 100+ LLM providers. The backend uses it
to reach OpenRouter. All LLM tasks (generation, evaluation, chat, PDF import) go through
the same call patterns.

### Install

```
uv add litellm
```

### Environment variable

```
OPENROUTER_API_KEY=sk-or-v1-...
```

LiteLLM reads `OPENROUTER_API_KEY` automatically when the model string is prefixed
with `openrouter/`. No other OpenRouter-specific config is required.

### Model string format

PLAN.md specifies `openai/gpt-oss-120b:free`. Prefix it for LiteLLM+OpenRouter:

```
openrouter/openai/gpt-oss-120b:free
```

General pattern: `openrouter/<provider>/<model-name>`.

---

### Non-streaming async completion

Used for generation and evaluation tasks where structured output is required.

```python
import litellm

response = await litellm.acompletion(
    model="openrouter/openai/gpt-oss-120b:free",
    messages=[
        {"role": "system", "content": "You are ResumeTailor-v2..."},
        {"role": "user",   "content": "Job description: ...\n\nMaster resume YAML: ..."},
    ],
)
text: str = response.choices[0].message.content
```

### Streaming async completion

Used for the chat assistant and any streamed generation path. Yields string deltas.

```python
response = await litellm.acompletion(
    model="openrouter/openai/gpt-oss-120b:free",
    messages=messages,
    stream=True,
)

async for chunk in response:
    delta = chunk.choices[0].delta.content
    if delta:
        yield delta  # push to SSE stream
```

### Structured output (JSON Schema)

Used when the backend needs a parsed object back — e.g. resume generation returning
validated YAML, or evaluation returning a scored result. Not all OpenRouter models
support strict structured output; test against the target model.

```python
import json

response = await litellm.acompletion(
    model="openrouter/openai/gpt-oss-120b:free",
    messages=messages,
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "evaluation_result",
            "schema": {
                "type": "object",
                "properties": {
                    "match_score":       {"type": "integer"},
                    "critique":          {"type": "string"},
                    "matched_keywords":  {"type": "array", "items": {"type": "string"}},
                    "missing_keywords":  {"type": "array", "items": {"type": "string"}},
                },
                "required": ["match_score", "critique", "matched_keywords", "missing_keywords"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
)

data = json.loads(response.choices[0].message.content)
# data["match_score"], data["critique"], etc.
```

Another example — resume generation returning YAML content:

```python
response = await litellm.acompletion(
    model="openrouter/openai/gpt-oss-120b:free",
    messages=messages,
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "tailored_resume",
            "schema": {
                "type": "object",
                "properties": {
                    "yaml_content": {"type": "string"},
                },
                "required": ["yaml_content"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
)

yaml_content: str = json.loads(response.choices[0].message.content)["yaml_content"]
```

### Two-step generation with audit (generation + critique passes)

PLAN.md's example prompts show a two-pass approach (generation → audit). Both use
`acompletion`; the second call receives the first response as user content:

```python
# Pass 1: generate
gen_response = await litellm.acompletion(
    model="openrouter/openai/gpt-oss-120b:free",
    messages=[
        {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
        {"role": "user",   "content": f"JD:\n{job_description}\n\nMaster:\n{master_yaml}"},
    ],
)
draft_yaml = gen_response.choices[0].message.content

# Pass 2: audit + correct
audit_response = await litellm.acompletion(
    model="openrouter/openai/gpt-oss-120b:free",
    messages=[
        {"role": "system", "content": CRITIQUE_SYSTEM_PROMPT},
        {"role": "user",   "content": f"Draft:\n{draft_yaml}\n\nMaster:\n{master_yaml}\n\nJD:\n{job_description}"},
    ],
)
final_yaml = audit_response.choices[0].message.content
# Strip AUDIT_START...AUDIT_END block from final_yaml before saving
```

### Error types

All LiteLLM exceptions live in `litellm.exceptions`.

```python
import litellm.exceptions as llm_exc

try:
    response = await litellm.acompletion(...)

except llm_exc.AuthenticationError:
    # Invalid or missing OPENROUTER_API_KEY → HTTP 401
    # Map to backend HTTP 500 (internal config error)
    pass

except llm_exc.RateLimitError:
    # OpenRouter rate limit hit → HTTP 429
    # Map to backend HTTP 503
    pass

except llm_exc.ServiceUnavailableError:
    # OpenRouter or upstream model unavailable → HTTP 503
    # Map to backend HTTP 503
    pass

except llm_exc.APIConnectionError:
    # Network failure, DNS error, timeout
    # Map to backend HTTP 503
    pass

except llm_exc.BadRequestError:
    # Malformed request — bad response_format, invalid messages, etc. → HTTP 400
    # Map to backend HTTP 500 (bug in backend prompt construction)
    pass

except llm_exc.ContextWindowExceededError:
    # Input too long for the model
    # Map to backend HTTP 400 (user's resume + JD too large)
    pass
```

---

## 2. render-cv (`rendercv`)

render-cv converts a YAML resume (render-cv format) into a PDF via a Typst compilation
pipeline. The backend uses it for:
- Generating PDFs for newly created tailored resumes
- Re-rendering PDFs after manual YAML edits

### ⚠️ PLAN.md Dockerfile discrepancy — Typst, not LaTeX

PLAN.md's Dockerfile section lists:
```
texlive-latex-base, texlive-latex-extra, texlive-fonts-recommended
```
**These are wrong for render-cv v2.x.** The v2.x pipeline is:

```
YAML → ruamel.yaml → Python dict → pydantic → RenderCVModel → jinja2 → .typ → typst → PDF
```

The PDF is compiled by the [`typst`](https://github.com/typst/typst) compiler, not LaTeX.
The `rendercv` pip package installs the `typst` Python binding as a dependency — no
system-level TeX installation is needed. **Update the Dockerfile accordingly.**

### Install

```
uv add rendercv
```

`rendercv` pulls in `typst` (Python binding) automatically.

---

### Option A: Subprocess (stable — recommended)

The CLI interface (`rendercv render`) is stable across render-cv versions. This is the
safest approach; the internal Python API is explicitly documented as unstable.

```python
import asyncio
import tempfile
from pathlib import Path


async def render_yaml_to_pdf(yaml_content: str) -> bytes:
    """Write YAML to a temp file, invoke rendercv CLI, return PDF bytes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        yaml_path = tmpdir_path / "resume.yaml"
        pdf_path  = tmpdir_path / "resume.pdf"

        yaml_path.write_text(yaml_content, encoding="utf-8")

        proc = await asyncio.create_subprocess_exec(
            "rendercv", "render", str(yaml_path),
            "--pdf-path",              str(pdf_path),
            "--dont-generate-markdown",
            "--dont-generate-html",
            "--dont-generate-png",
            "--dont-generate-typst",   # skip keeping the .typ intermediate file
            "--quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"rendercv exited {proc.returncode}: {stderr.decode('utf-8', errors='replace')}"
            )

        return pdf_path.read_bytes()
```

### Option B: In-process Python API (faster; internal — may change between versions)

The internal functions avoid subprocess overhead. Verify function names against the
installed version of rendercv before using.

```python
import tempfile
from pathlib import Path


def render_yaml_to_pdf_inprocess(yaml_content: str) -> bytes:
    """In-process render via rendercv internals. Fast but uses private API."""
    from rendercv import data     as rendercv_data
    from rendercv import renderer as rendercv_renderer

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        yaml_path   = tmpdir_path / "resume.yaml"
        yaml_path.write_text(yaml_content, encoding="utf-8")

        # Step 1: Parse YAML → RenderCVModel (also validates against pydantic schema)
        resume_model = rendercv_data.read_input_file(yaml_path)

        # Step 2: Render to files; PDF ends up in tmpdir/rendercv_output/<Name>_CV.pdf
        rendercv_renderer.render_a_resume_to_pdfs(
            resume_model,
            output_folder_as_a_path=tmpdir_path,
        )

        pdf_files = list(tmpdir_path.glob("**/*.pdf"))
        if not pdf_files:
            raise RuntimeError("rendercv produced no PDF output")

        return pdf_files[0].read_bytes()
```

> If `rendercv_data.read_input_file` or `rendercv_renderer.render_a_resume_to_pdfs`
> do not exist in the installed version, inspect the package: `python -c "import rendercv; help(rendercv)"`.
> Fall back to Option A (subprocess) if needed.

### YAML validation

render-cv validates the YAML against its Pydantic schema when parsing. Validation errors
should be surfaced to the API caller as HTTP 422:

```python
import pydantic
from rendercv import data as rendercv_data

try:
    resume_model = rendercv_data.read_input_file(yaml_path)
except pydantic.ValidationError as exc:
    # e.errors() is a list of dicts with loc, msg, type
    raise ValueError(f"Invalid render-cv YAML: {exc}") from exc
except Exception as exc:
    raise ValueError(f"Failed to parse YAML: {exc}") from exc
```

### YAML Schema

The schema for render-cv YAML (used in the example master resume):

```
https://raw.githubusercontent.com/rendercv/rendercv/refs/tags/v2.8/schema.json
```

---

## 3. PyMuPDF

PyMuPDF (`pymupdf`) extracts plain text from PDF bytes for the PDF import feature
(`POST /api/master-resume/import`). The extracted text is sent to the LLM which converts
it to render-cv YAML.

### Install

```
uv add pymupdf
```

### Open from bytes and extract text

```python
import pymupdf  # the package name is pymupdf; it exposes the fitz API


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from a PDF supplied as bytes.

    Enforces PLAN.md constraints: max 10 MB, max 50 pages.
    Returns a single string with pages separated by double newlines.
    """
    MAX_BYTES = 10 * 1024 * 1024  # 10 MB
    MAX_PAGES = 50

    if len(pdf_bytes) > MAX_BYTES:
        raise ValueError(f"PDF exceeds 10 MB limit ({len(pdf_bytes)} bytes)")

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")

    if doc.page_count > MAX_PAGES:
        doc.close()
        raise ValueError(f"PDF has {doc.page_count} pages (max {MAX_PAGES})")

    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text())  # plain text, reading order

    doc.close()
    return "\n\n".join(pages)
```

### Text extraction options

`page.get_text(opt)` accepts several format strings:

| `opt` value | Output | Use case |
|-------------|--------|----------|
| `"text"` (default) | Plain text, natural reading order | Resume import (sufficient for LLM) |
| `"blocks"` | List of `(x0, y0, x1, y1, text, ...)` tuples | Layout-aware extraction |
| `"dict"` | Full structured dict with fonts, colors, spans | Detailed analysis |
| `"html"` | HTML string | Embedding in web contexts |

For resume PDF import, `"text"` is correct — the LLM only needs the raw content, not
positional metadata.

### Errors to handle

```python
try:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
except Exception as exc:
    # Corrupt, password-protected, or non-PDF bytes
    raise ValueError(f"Cannot open PDF: {exc}") from exc
```

PyMuPDF raises generic `Exception` (or `RuntimeError`) for malformed input — there is no
dedicated exception class to `except` against. Catch `Exception` and re-raise as a domain
error.
