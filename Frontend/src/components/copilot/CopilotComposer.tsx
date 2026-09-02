import { useState } from "react";
import { Send, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";

export function CopilotComposer({
  disabled,
  pending,
  hasMessages,
  onSend,
  onClear,
}: {
  disabled: boolean;
  pending: boolean;
  hasMessages: boolean;
  onSend: (text: string) => void;
  onClear: () => void;
}) {
  const [draft, setDraft] = useState("");

  const submit = () => {
    if (!draft.trim() || pending || disabled) return;
    onSend(draft);
    setDraft("");
  };

  return (
    <div className="w-full">
      <div className="flex items-end gap-2">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          disabled={disabled}
          rows={1}
          placeholder={disabled ? "Open a reconciliation to ask a question…" : "Ask about this reconciliation…"}
          className="max-h-28 min-h-[38px] flex-1 resize-none rounded-lg border border-line bg-surface px-3 py-2.5 text-[13px] text-ink placeholder:text-ink-3 transition-[border-color,box-shadow] duration-150 hover:border-line-strong focus:border-accent focus:outline-none focus:ring-3 focus:ring-accent/12 disabled:cursor-not-allowed disabled:opacity-60"
        />
        <Button size="md" onClick={submit} disabled={disabled || pending || !draft.trim()} aria-label="Send message">
          <Send className="size-4" />
        </Button>
      </div>
      <div className="mt-2 flex items-center justify-between">
        <span className="text-[10.5px] text-ink-3">Enter to send · Shift+Enter for a new line</span>
        {hasMessages && (
          <button
            onClick={onClear}
            className="inline-flex items-center gap-1 text-[10.5px] font-medium text-ink-3 transition-colors hover:text-ink-2"
          >
            <Trash2 className="size-3" /> Clear conversation
          </button>
        )}
      </div>
    </div>
  );
}
