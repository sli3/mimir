"""
wiki_search_mcp.py — MCP server exposing mimir-wiki ChromaDB search.

Legal: Receive-only project. This tool has no RF/hardware access at all —
it only queries a local ChromaDB vector store and a local embedding
endpoint. Included here purely for consistency with the rest of Mimir's
tooling conventions (docstrings, error messages).

This is a direct translation of the existing .opencode/tool/wiki-search.js
OpenCode custom tool into an MCP server, so the same search capability can
be used outside OpenCode by any MCP-compatible client. The query logic,
error messages, and result formatting are intentionally kept equivalent
to the JS version — if one changes, update the other, or retire one in
favour of the other to avoid drift between two implementations of the
same tool.

Transport: stdio. This server is intended to be spawned as a local
subprocess by a single MCP client (OpenCode) on the same machine — see
the project's design conversation for why stdio was chosen over
Streamable HTTP: local, single-user, no auth/audit/multi-tenancy need.

Configuration must match the values used by index_wiki.py in the
mimir-wiki repo. If either endpoint ever moves, update both places.
"""

import logging

import httpx
from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)

EMBEDDING_ENDPOINT = "http://192.168.0.66:8081/v1/embeddings"
EMBEDDING_MODEL = "Qwen3-Embedding-0.6B"

CHROMADB_HOST = "192.168.0.10"
CHROMADB_PORT = 8558
CHROMADB_BASE_URL = f"http://{CHROMADB_HOST}:{CHROMADB_PORT}"
COLLECTION_NAME = "mimir_wiki"

# ChromaDB's default tenant/database in v2, unless configured otherwise.
TENANT = "default_tenant"
DATABASE = "default_database"

# Shared async HTTP client, reused across calls rather than opened fresh
# per request — this server is a long-lived stdio subprocess, so a
# persistent connection pool is the correct choice here (unlike a
# request-scoped web handler, where opening fresh per request is normal).
_http_client = httpx.AsyncClient(timeout=30.0)

server = MCPServer(
    name="mimir-wiki-search",
    description=(
        "Search the mimir-wiki knowledge base for relevant gotchas, design "
        "decisions, hardware findings, and past dev-session context."
    ),
)


async def _embed_query(query: str) -> list[float]:
    """Embed a query string via yubaba's Qwen3-Embedding-0.6B endpoint."""
    response = await _http_client.post(
        EMBEDDING_ENDPOINT,
        json={"model": EMBEDDING_MODEL, "input": query},
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Embedding server returned {response.status_code} "
            f"{response.reason_phrase}. {response.text}"
        )

    data = response.json()
    vector = (data.get("data") or [{}])[0].get("embedding")
    if not isinstance(vector, list) or len(vector) == 0:
        raise RuntimeError("Embedding server responded but returned no vector.")
    return vector


async def _get_collection_id() -> str:
    """Look up the collection's UUID by name.

    ChromaDB's v2 query endpoint is keyed by collection ID, not name, so
    this is a required first step before every query.
    """
    url = (
        f"{CHROMADB_BASE_URL}/api/v2/tenants/{TENANT}/databases/"
        f"{DATABASE}/collections/{COLLECTION_NAME}"
    )
    response = await _http_client.get(url)
    if response.status_code >= 400:
        raise RuntimeError(
            f'Could not find collection "{COLLECTION_NAME}" on ChromaDB '
            f"({response.status_code}). {response.text}"
        )

    data = response.json()
    collection_id = data.get("id")
    if not collection_id:
        raise RuntimeError(
            f'Collection "{COLLECTION_NAME}" response had no id field.'
        )
    return collection_id


async def _query_collection(collection_id: str, vector: list[float], k: int) -> dict:
    """Query the collection for the k nearest notes to the given embedding."""
    url = (
        f"{CHROMADB_BASE_URL}/api/v2/tenants/{TENANT}/databases/"
        f"{DATABASE}/collections/{collection_id}/query"
    )
    response = await _http_client.post(
        url,
        json={
            "query_embeddings": [vector],
            "n_results": k,
            "include": ["documents", "metadatas", "distances"],
        },
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"ChromaDB query failed ({response.status_code}). {response.text}"
        )
    return response.json()


def _format_results(result: dict) -> str:
    """Format ChromaDB's query result into readable text for the agent."""
    ids = (result.get("ids") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    if len(ids) == 0:
        return "No relevant wiki notes found for this query."

    sections = []
    for i, note_id in enumerate(ids):
        path = (metadatas[i] or {}).get("path") if i < len(metadatas) else None
        path = path or note_id
        distance = distances[i] if i < len(distances) else None
        distance_str = f"{distance:.4f}" if isinstance(distance, (int, float)) else "?"
        text = documents[i] if i < len(documents) and documents[i] else "(no content)"
        sections.append(f"### {path}  (distance: {distance_str})\n\n{text}")

    header = f"Found {len(ids)} relevant note(s) in mimir-wiki:\n\n"
    return header + "\n\n---\n\n".join(sections)


@server.tool()
async def wikisearch(query: str, limit: int = 5) -> str:
    """Search the mimir-wiki knowledge base for relevant gotchas, design
    decisions, hardware findings, and past dev-session context.

    Use this before implementing or debugging anything that touches an
    area the wiki might already document (e.g. RF hardware quirks,
    calibration, dashboard behaviour, decoder edge cases). Query with a
    few descriptive keywords, similar to a search engine query, not a
    full sentence.

    Args:
        query: Search terms describing what you're looking for, e.g.
            "Pluto gain threshold calibration".
        limit: Maximum number of notes to return, 1-15 (default 5).

    Returns:
        Formatted text listing the matching wiki notes, or a message
        stating none were found.
    """
    # Clamp rather than reject — matches the JS tool's schema-enforced
    # min(1)/max(15)/default(5), since this SDK's plain type hints don't
    # give us that declarative validation for free.
    limit = max(1, min(15, limit))

    try:
        vector = await _embed_query(query)
        collection_id = await _get_collection_id()
        result = await _query_collection(collection_id, vector, limit)
        return _format_results(result)
    except Exception as exc:  # noqa: BLE001 - deliberately broad, matches
        # the JS tool's catch-all: any failure here should degrade to a
        # readable message for the calling agent, not a crashed tool call.
        logger.exception("Wiki search failed")
        return (
            f"Wiki search failed: {exc}\n\n"
            f"Check that yubaba's embedding server (:8081) and ChromaDB "
            f"({CHROMADB_HOST}:{CHROMADB_PORT}) are both running."
        )


if __name__ == "__main__":
    server.run(transport="stdio")
