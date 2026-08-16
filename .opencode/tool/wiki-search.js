import { tool } from "@opencode-ai/plugin"

// ---------------------------------------------------------------------------
// Configuration - must match the values used by index_wiki.py in the
// mimir-wiki repo. If either endpoint ever moves, update both places.
// ---------------------------------------------------------------------------

const EMBEDDING_ENDPOINT = "http://192.168.0.66:8081/v1/embeddings"
const EMBEDDING_MODEL = "Qwen3-Embedding-0.6B"

const CHROMADB_HOST = "192.168.0.10"
const CHROMADB_PORT = 8558
const CHROMADB_BASE_URL = `http://${CHROMADB_HOST}:${CHROMADB_PORT}`
const COLLECTION_NAME = "mimir_wiki"

// ChromaDB's default tenant/database in v2, unless configured otherwise.
const TENANT = "default_tenant"
const DATABASE = "default_database"

/**
 * Embed a query string via yubaba's Qwen3-Embedding-0.6B endpoint.
 */
async function embedQuery(query) {
  const response = await fetch(EMBEDDING_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: EMBEDDING_MODEL, input: query }),
  })

  if (!response.ok) {
    const body = await response.text().catch(() => "")
    throw new Error(
      `Embedding server returned ${response.status} ${response.statusText}. ${body}`
    )
  }

  const data = await response.json()
  const vector = data?.data?.[0]?.embedding
  if (!Array.isArray(vector) || vector.length === 0) {
    throw new Error("Embedding server responded but returned no vector.")
  }
  return vector
}

/**
 * Look up the collection's UUID by name. ChromaDB's v2 query endpoint is
 * keyed by collection ID, not name, so this is a required first step.
 */
async function getCollectionId() {
  const url = `${CHROMADB_BASE_URL}/api/v2/tenants/${TENANT}/databases/${DATABASE}/collections/${COLLECTION_NAME}`
  const response = await fetch(url)

  if (!response.ok) {
    const body = await response.text().catch(() => "")
    throw new Error(
      `Could not find collection "${COLLECTION_NAME}" on ChromaDB (${response.status}). ${body}`
    )
  }

  const data = await response.json()
  if (!data?.id) {
    throw new Error(`Collection "${COLLECTION_NAME}" response had no id field.`)
  }
  return data.id
}

/**
 * Query the collection for the k nearest notes to the given embedding.
 */
async function queryCollection(collectionId, vector, k) {
  const url = `${CHROMADB_BASE_URL}/api/v2/tenants/${TENANT}/databases/${DATABASE}/collections/${collectionId}/query`
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query_embeddings: [vector],
      n_results: k,
      include: ["documents", "metadatas", "distances"],
    }),
  })

  if (!response.ok) {
    const body = await response.text().catch(() => "")
    throw new Error(`ChromaDB query failed (${response.status}). ${body}`)
  }

  return response.json()
}

/**
 * Format ChromaDB's query result into readable text for the agent.
 */
function formatResults(result) {
  const ids = result?.ids?.[0] ?? []
  const documents = result?.documents?.[0] ?? []
  const metadatas = result?.metadatas?.[0] ?? []
  const distances = result?.distances?.[0] ?? []

  if (ids.length === 0) {
    return "No relevant wiki notes found for this query."
  }

  const sections = ids.map((id, i) => {
    const path = metadatas[i]?.path ?? id
    const distance = typeof distances[i] === "number" ? distances[i].toFixed(4) : "?"
    const text = documents[i] ?? "(no content)"
    return `### ${path}  (distance: ${distance})\n\n${text}`
  })

  return (
    `Found ${ids.length} relevant note(s) in mimir-wiki:\n\n` +
    sections.join("\n\n---\n\n")
  )
}

export default tool({
  description:
    "Search the mimir-wiki knowledge base for relevant gotchas, design decisions, " +
    "hardware findings, and past dev-session context. Use this before implementing " +
    "or debugging anything that touches an area the wiki might already document " +
    "(e.g. RF hardware quirks, calibration, dashboard behaviour, decoder edge cases). " +
    "Query with a few descriptive keywords, similar to a search engine query, not a " +
    "full sentence.",
  args: {
    query: tool.schema
      .string()
      .describe("Search terms describing what you're looking for, e.g. 'Pluto gain threshold calibration'"),
    limit: tool.schema
      .number()
      .min(1)
      .max(15)
      .default(5)
      .describe("Maximum number of notes to return (default 5)"),
  },
  async execute(args) {
    try {
      const vector = await embedQuery(args.query)
      const collectionId = await getCollectionId()
      const result = await queryCollection(collectionId, vector, args.limit)
      return formatResults(result)
    } catch (error) {
      return (
        `Wiki search failed: ${error.message}\n\n` +
        `Check that yubaba's embedding server (:8081) and ChromaDB (${CHROMADB_HOST}:${CHROMADB_PORT}) are both running.`
      )
    }
  },
})
