import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "@/services/api";
import type { CopilotChatMessage, CopilotResponse } from "@/services/types";

export interface CopilotDisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  at: string;
  response?: CopilotResponse;
  error?: boolean;
}

let seq = 0;
const nextId = () => `copilot-${Date.now()}-${seq++}`;

/** Older turns beyond this are dropped client-side too — mirrors the
 * backend's own cap, keeps the request small regardless of how long the
 * conversation runs. */
const MAX_HISTORY_TURNS = 10;

function toHistory(messages: CopilotDisplayMessage[]): CopilotChatMessage[] {
  return messages
    .filter((m) => !m.error)
    .slice(-MAX_HISTORY_TURNS)
    .map((m) => ({ role: m.role, content: m.content }));
}

/**
 * Chat state for one reconciliation job. Conversation memory lives only in
 * this hook's state (the backend endpoint is stateless) and resets whenever
 * `jobId` changes, so nothing can leak between reconciliation runs.
 */
export function useCopilotChat(jobId: string | null) {
  const [messages, setMessages] = useState<CopilotDisplayMessage[]>([]);
  const [pending, setPending] = useState(false);
  const conversationId = useRef(`conv-${Math.random().toString(36).slice(2)}`);

  useEffect(() => {
    setMessages([]);
    setPending(false);
  }, [jobId]);

  const runTurn = useCallback(
    async (text: string, history: CopilotChatMessage[]) => {
      if (!jobId) return;
      setPending(true);
      try {
        const response = await api.askCopilot(jobId, text, history, conversationId.current);
        setMessages((prev) => [
          ...prev,
          { id: nextId(), role: "assistant", content: response.answer, at: new Date().toISOString(), response },
        ]);
      } catch (err) {
        const message =
          err instanceof api.ApiError
            ? err.message
            : "The Copilot could not reach the server. Please try again.";
        setMessages((prev) => [
          ...prev,
          { id: nextId(), role: "assistant", content: message, at: new Date().toISOString(), error: true },
        ]);
      } finally {
        setPending(false);
      }
    },
    [jobId],
  );

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || !jobId || pending) return;
      const history = toHistory(messages);
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "user", content: trimmed, at: new Date().toISOString() },
      ]);
      void runTurn(trimmed, history);
    },
    [jobId, pending, messages, runTurn],
  );

  /** Drops the failed reply and re-asks the same question with the same
   * history it originally had — never duplicates the user's bubble. */
  const retry = useCallback(() => {
    setMessages((prev) => {
      let lastUserIdx = -1;
      for (let i = prev.length - 1; i >= 0; i--) {
        if (prev[i].role === "user") {
          lastUserIdx = i;
          break;
        }
      }
      if (lastUserIdx === -1) return prev;
      const text = prev[lastUserIdx].content;
      const history = toHistory(prev.slice(0, lastUserIdx));
      void runTurn(text, history);
      return prev.slice(0, lastUserIdx + 1);
    });
  }, [runTurn]);

  const clear = useCallback(() => setMessages([]), []);

  return { messages, pending, send, retry, clear };
}
