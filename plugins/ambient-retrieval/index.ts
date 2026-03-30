/**
 * ambient-retrieval — wraps lossless-claw context engine and injects
 * relevant QMD search results into the system prompt before each agent turn.
 *
 * Architecture:
 * - Registers as "ambient-retrieval" context engine
 * - Lazily acquires lossless-claw's engine instance from the globalThis registry
 * - Delegates ALL lossless-claw methods (compaction, ingest, bootstrap, etc.)
 * - Adds one thing in assemble(): run QMD search on the last user message,
 *   merge results into systemPromptAddition
 * - All errors are caught silently — never breaks a turn
 */

import { execSync } from "node:child_process";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk";

const QMD_BIN = "/usr/local/bin/qmd";
const ENGINE_REGISTRY_KEY = "__openclaw_context_engine_registry__";
const MIN_QUERY_LENGTH = 8;
const MAX_RESULTS = 3;
const QMD_TIMEOUT_MS = 2500;
// Simple word list to skip qmd search when the message is clearly not about prior context
const SKIP_PATTERNS = [/^heartbeat/i, /^\/status/i, /^\/model/i];

/** Safely extract text from a message content (string or block array). */
function extractMessageText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .filter((b): b is { type: string; text: string } => !!b && typeof b === "object" && b.type === "text" && typeof b.text === "string")
      .map((b) => b.text)
      .join(" ");
  }
  return "";
}

/** Get the lossless-claw engine instance from the globalThis registry, lazily. */
function getLcmEngineFactory(): (() => Promise<unknown>) | undefined {
  const registry = (globalThis as Record<string, unknown>)[ENGINE_REGISTRY_KEY] as
    | { engines?: Map<string, () => unknown> }
    | undefined;
  return registry?.engines?.get("lossless-claw") as (() => Promise<unknown>) | undefined;
}

/** Run QMD search and return a formatted snippet string, or null if nothing useful. */
function runQmdSearch(query: string): string | null {
  try {
    // Sanitize: strip quotes and control chars, truncate
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

// Minimal type for context engine interface
type AnyEngine = {
  info?: { ownsCompaction?: boolean };
  bootstrap?: (p: unknown) => Promise<unknown>;
  ingest?: (p: unknown) => Promise<unknown>;
  ingestBatch?: (p: unknown) => Promise<unknown>;
  assemble?: (p: { sessionId: string; messages: unknown[]; tokenBudget?: number }) => Promise<{
    messages: unknown[];
    estimatedTokens?: number;
    systemPromptAddition?: string;
  }>;
  afterTurn?: (p: unknown) => Promise<unknown>;
  compact?: (p: unknown) => Promise<unknown>;
  dispose?: () => Promise<void>;
};

const ambientRetrievalPlugin = {
  id: "ambient-retrieval",
  name: "Ambient Retrieval",
  description: "Wraps lossless-claw and injects QMD search results into system prompt before each turn",

  register(api: OpenClawPluginApi) {
    let lcmInstance: AnyEngine | null = null;
    let lcmInitAttempted = false;

    /** Lazily initialize the lossless-claw engine. Called on first use. */
    async function ensureLcm(): Promise<AnyEngine | null> {
      if (lcmInitAttempted) return lcmInstance;
      lcmInitAttempted = true;
      try {
        const factory = getLcmEngineFactory();
        if (!factory) {
          api.logger.warn("[ambient-retrieval] lossless-claw engine factory not found — running without LCM");
          return null;
        }
        lcmInstance = (await factory()) as AnyEngine;
        api.logger.info("[ambient-retrieval] lossless-claw engine acquired");
      } catch (err) {
        api.logger.warn(`[ambient-retrieval] Failed to initialize lossless-claw engine: ${String(err)}`);
      }
      return lcmInstance;
    }

    api.registerContextEngine("ambient-retrieval", () => ({
      get info() {
        // Reflect lossless-claw's compaction ownership so the gateway behaves identically
        return lcmInstance?.info ?? { ownsCompaction: true };
      },

      async bootstrap(params: unknown) {
        const lcm = await ensureLcm();
        return lcm?.bootstrap?.(params);
      },

      async ingest(params: unknown) {
        const lcm = await ensureLcm();
        return lcm?.ingest?.(params) ?? { ingested: false };
      },

      async ingestBatch(params: unknown) {
        const lcm = await ensureLcm();
        return lcm?.ingestBatch?.(params);
      },

      async assemble(params: { sessionId: string; messages: unknown[]; tokenBudget?: number }) {
        const lcm = await ensureLcm();

        // Get lossless-claw's result first (summaries, compacted context, etc.)
        const lcmResult = lcm?.assemble
          ? await lcm.assemble(params).catch(() => ({ messages: params.messages, estimatedTokens: 0 }))
          : { messages: params.messages, estimatedTokens: 0 };

        // Find last user message
        const msgs = lcmResult.messages ?? params.messages;
        const lastUser = [...(msgs as { role?: string; content?: unknown }[])]
          .reverse()
          .find((m) => m.role === "user");

        if (!lastUser) return lcmResult;

        const queryText = extractMessageText(lastUser.content);
        if (!queryText || queryText.length < MIN_QUERY_LENGTH) return lcmResult;

        // Run QMD search — this is the ambient retrieval step
        const qmdSnippet = runQmdSearch(queryText);

        if (!qmdSnippet) return lcmResult;

        // Merge with any existing systemPromptAddition from lossless-claw
        const combined = lcmResult.systemPromptAddition
          ? `${lcmResult.systemPromptAddition}\n\n${qmdSnippet}`
          : qmdSnippet;

        api.logger.debug(`[ambient-retrieval] injected ${qmdSnippet.length} chars of QMD context`);

        return { ...lcmResult, systemPromptAddition: combined };
      },

      async afterTurn(params: unknown) {
        const lcm = await ensureLcm();
        return lcm?.afterTurn?.(params);
      },

      async compact(params: unknown) {
        const lcm = await ensureLcm();
        if (!lcm?.compact) {
          return { ok: false, compacted: false, reason: "lossless-claw engine unavailable" };
        }
        return lcm.compact(params);
      },

      async dispose() {
        const lcm = await ensureLcm();
        return lcm?.dispose?.();
      },
    }));

    api.logger.info("[ambient-retrieval] Plugin loaded");
  },
};

export default ambientRetrievalPlugin;
