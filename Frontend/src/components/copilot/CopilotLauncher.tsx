import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Drawer } from "@/components/ui/Drawer";
import { Badge } from "@/components/ui/Badge";
import { useRecon } from "@/store/ReconProvider";
import { CopilotAvatar } from "./CopilotAvatar";
import { CopilotComposer } from "./CopilotComposer";
import { CopilotMessages } from "./CopilotMessages";
import { useCopilotChat } from "./useCopilotChat";

/**
 * Global entry point for the Reconciliation Copilot: a floating "Ask
 * ReconIQ" launcher, docked bottom-right on every page, plus the drawer it
 * opens. Mounted once in AppShell so it follows the user across the app and
 * always reflects whichever reconciliation is currently active.
 */
export function CopilotLauncher() {
  const [open, setOpen] = useState(false);
  const { jobId, summary } = useRecon();
  const activeJobId = summary?.jobId ?? jobId;
  const { messages, pending, send, retry, clear } = useCopilotChat(activeJobId);

  return (
    <>
      <AnimatePresence>
        {!open && (
          <motion.button
            key="copilot-launcher"
            onClick={() => setOpen(true)}
            initial={{ opacity: 0, y: 10, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.9 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 rounded-full border border-ai-line bg-surface px-4 py-2.5 text-[13px] font-semibold text-ai-text shadow-lg transition-transform duration-150 hover:scale-[1.03] active:scale-[0.98]"
          >
            <CopilotAvatar state="idle" size={22} />
            Ask ReconIQ
          </motion.button>
        )}
      </AnimatePresence>

      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        width={440}
        headerAccessory={<CopilotAvatar state={pending ? "thinking" : "idle"} size={30} />}
        title="ReconIQ Copilot"
        subtitle={
          <span className="flex flex-wrap items-center gap-1.5">
            <Badge tone="ai" size="sm">Read-only</Badge>
            <span className="text-ink-3">·</span>
            {activeJobId ? (
              <span className="tnum">{activeJobId}</span>
            ) : (
              <span>No reconciliation selected</span>
            )}
            <span className="text-ink-3">·</span>
            <span>Grounded in ReconIQ data</span>
          </span>
        }
        footer={
          <CopilotComposer
            disabled={!activeJobId}
            pending={pending}
            hasMessages={messages.length > 0}
            onSend={send}
            onClear={clear}
          />
        }
      >
        <CopilotMessages
          jobId={activeJobId}
          messages={messages}
          pending={pending}
          onSend={send}
          onRetry={retry}
        />
      </Drawer>
    </>
  );
}
