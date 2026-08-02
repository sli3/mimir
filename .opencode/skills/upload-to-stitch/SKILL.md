---
name: upload-to-stitch
description: >-
  Upload local assets (images, mockups, extracted HTML, design markdown) to a Stitch project.
  ALWAYS use this skill when you need to upload visual assets, HTML pages, or design docs
  to Stitch, particularly when direct MCP tool calls fail or truncate due to
  base64 token limits.
allowed-tools:
  - "stitch_*"
  - "bash"
  - "read"
  - "write"
  - "webfetch"
---

# Upload-to-Stitch

Upload local assets (images, mockups, HTML, and markdown files) to a Stitch project using the
provided upload script, which bypasses the MCP tool's base64 output token limits.

> **Why this exists:** the AI model cannot upload files via MCP tools
> directly because the base64 encoding of even a small file exceeds the
> model's output token limit (~16K tokens). This script reads the file and
> sends it directly over HTTP, bypassing the model entirely.

## Credential sourcing — Mimir-specific, read before using

> **This is the one deliberate change from the upstream skill.** The
> original version instructs the agent to locate and read the Stitch API
> key out of an agent config file on disk (`~/.claude.json`,
> `.gemini/antigravity/mcp_config.json`, etc.) and pass it as a plaintext
> CLI argument. **Do not do that in this project.** This project's Stitch
> API key is already stored as the `GOOGLE_STITCH_API_KEY` fish universal
> variable and resolved via `{env:GOOGLE_STITCH_API_KEY}` in `opencode.json`
> for the MCP connection itself — the same mechanism should supply it here.
>
> Source the key by running the script with the environment variable
> expanded by the shell, e.g.:
> ```bash
> python3 .opencode/skills/upload-to-stitch/scripts/upload_to_stitch.py \
>   --project-id <PROJECT_ID> \
>   --file-path <PATH_TO_FILE> \
>   --api-key "$GOOGLE_STITCH_API_KEY"
> ```
> Never read, cat, grep, or otherwise inspect any agent config file to find
> this key — it is not stored there in this project, and there is no reason
> to go looking.

## Steps

### 1. Identify Target Project

Use `stitch_list_projects` to find the correct `projectId`.

### 2. Confirm the API Key is Available

Verify the environment variable is set before attempting the upload:

```bash
[ -n "$GOOGLE_STITCH_API_KEY" ] && echo "present" || echo "MISSING — do not proceed"
```

If missing, stop and tell the user — do not attempt to source the key from
any other location. This is a hard stop, not a fallback-and-continue case.

### 3. Run Upload Script

> **Checkpoint — User Confirmation Required.**
> Before running the upload script, you **MUST** pause and present the
> file(s) to be uploaded (paths, sizes, and types) to the user and wait for
> explicit approval. Do **NOT** execute the upload script until the user
> confirms. This gate is preserved unchanged from the upstream skill and
> must not be skipped, including on repeat uploads within the same session.

```bash
python3 .opencode/skills/upload-to-stitch/scripts/upload_to_stitch.py \
  --project-id <PROJECT_ID> \
  --file-path <PATH_TO_FILE> \
  --api-key "$GOOGLE_STITCH_API_KEY" \
  [--title <SCREEN_TITLE>] \
  [--generated-by <GENERATED_BY>]
```

> **macOS / SSL Certificate Troubleshooting** (unlikely on this project's
> Fedora 44 dev environment, kept for completeness):
> If the upload fails with `ssl.SSLCertVerificationError`, the script
> automatically attempts to use the `certifi` package to load the CA bundle
> if installed. If not installed: `pip install certifi --break-system-packages`
> (per this project's pip convention), or manually supply
> `SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")`
> before the command above.

### Supported File Types

| Extension | MIME Type |
|:---|:---|
| `.png` | `image/png` |
| `.jpg`, `.jpeg` | `image/jpeg` |
| `.webp` | `image/webp` |
| `.html`, `.htm` | `text/html` |
| `.md` | `text/markdown` |

The script auto-detects MIME type from the file extension.

### Script Options

- `--project-id`: **Required**. The Stitch project ID.
- `--file-path`: **Required**. Path to the local file to upload.
- `--api-key`: **Required**. Source from `$GOOGLE_STITCH_API_KEY` — see
  credential sourcing note above.
- `--api-url`: Optional. Base URL of the Stitch API. Defaults to `https://stitch.googleapis.com`.
- `--title`: Optional. Title for the uploaded screen. When uploading extracted HTML from a web app, set this to the **route path** of the page (e.g., `/vectordb`, `/radar`) so the screen name in Stitch clearly identifies the route.
- `--generated-by`: Optional. Specify how the uploaded file was generated (e.g. `extract-design-md`, `manage-design-system`, or the agent name).

## Compatibility notes (OpenCode / Mimir)

- `scripts/upload_to_stitch.py` ported **verbatim** — it is credential-agnostic
  (accepts `--api-key` as a plain string regardless of source) and required
  no code changes.
- The only substantive change from upstream is the credential-sourcing
  instructions: replaced "read the key from an agent config file" with
  "source from the `$GOOGLE_STITCH_API_KEY` environment variable already in
  use for this project's Stitch MCP connection." Added a hard-stop check
  (Step 2) rather than letting the agent silently search other locations if
  the variable is unset.
- `allowed-tools` lowercased for OpenCode convention; `web_fetch` → `webfetch`.
- The user-confirmation checkpoint before running the upload is preserved
  unchanged — this is a genuine safety gate (irreversible external upload
  with a real API call), not boilerplate to streamline away.
