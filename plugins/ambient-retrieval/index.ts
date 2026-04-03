/**
 * ambient-retrieval — injects relevant QMD search results into the system
 * prompt before each agent turn.
 *
 * Architecture (v2):
 * - Registers as "ambient-retrieval" context engine
 * - Does NOT proxy or wrap lossless-claw — compaction is delegated to runtime
 * - Only does one thing in assemble(): run QMD search on the last user message
 *   and inject results as systemPromptAddition
 * - All errors caught silently — never breaks a turn
 *
 * To use: set plugins.slots.contextEngine = "ambient-retrieval" in openclaw.json
 * lossless-claw compaction still works via delegateCompactionToRuntime.
 */

import { execSync } from "node:child_process";
import { delegateCompactionToRuntime } from "openclaw/plugin-sdk/core";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk";

const QMD_BIN = "/usr/local/bin/qmd";
const MIN_QUERY_LENGTH = 8;
const MAX_RESULTS = 3;
const QMD_TIMEOUT_MS = 2500;
const SKIP_PATTERNS = [/^heartbeat/i, /^\/status/i, /^\/model/i, /^\/compact/i];

/** Safely extract text from a message content (string or block array). */
function extractMessageText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .filter((b): b is { type: string; text: string } =>
        !!b && typeof b === "object" && b.type === "text" && typeof b.text === "string"
      )
      .map((b) => b.text)
      .join(" ");
  }
  return "";
}

/** Run QMD search and return a formatted snippet string, or null if nothing useful. */
function runQmdSearch(query: string): string | null {
  try {
    const sanitized = query.replace(/["\n\r\t]/g, " ").replace(/\s+/g, " ").trim().slice(0, 200);
    if (sanitized.length < MIN_QUERY_LENGTH) return null;
    if (SKIP_PATTERNS.some((p) => p.test(sanitized))) return null;

    const output = execSync(`${QMD_BIN} query ${JSON.stringify(sanitized)} -n ${MAX_RESULTS} --md`, {
      encoding: "utf8",
      timeout: QMD_TIMEOUT_MS,
    }).trim();

    if (!output || output === "(no results)") return null;
    return `## Ambient context (auto-retrieved from knowledge base):\n${output}`;
  } catch {
    return null;
  }
}

const ambientRetrievalPlugin = {
  id: "ambient-retrieval",
  name: "Ambient Retrieval",
  description: "Injects QMD search results into system prompt before each turn. Delegates compaction to runtime.",

  register(api: OpenClawPluginApi) {
    api.registerContextEngine("ambient-retrieval", () => ({
      info: {
        id: "ambient-retrieval",
        ownsCompaction: false,
      },

      async ingest() {
        return { ingested: false };
      },

      async ingestBatch() {
        return { ingested: false };
      },

      async assemble(params: { sessionId: string; messages: unknown[]; tokenBudget?: number }) {
        const msgs = params.messages as { role?: string; content?: unknown }[];

        // Find last user message and run QMD search
        const lastUser = [...msgs].reverse().find((m) => m.role === "user");
        if (!lastUser) return { messages: params.messages };

        const queryText = extractMessageText(lastUser.content);
        const qmdSnippet = queryText ? runQmdSearch(queryText) : null;

        if (qmdSnippet) {
          api.logger.debug(`[ambient-retrieval] injected ${qmdSnippet.length} chars of QMD context`);
          return { messages: params.messages, systemPromptAddition: qmdSnippet };
        }

        return { messages: params.messages };
      },

      async compact(params: unknown) {
        // Delegate to runtime — this triggers lossless-claw or whatever the
        // runtime's built-in compaction is, without us needing to proxy it.
        return delegateCompactionToRuntime(params);
      },
    }));

    api.logger.info("[ambient-retrieval] Plugin loaded (v2 — runtime compaction delegation)");
  },
};

export default ambientRetrievalPlugin;
