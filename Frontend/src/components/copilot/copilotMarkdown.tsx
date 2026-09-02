import type { ReactNode } from "react";

/**
 * A tiny, purpose-built renderer for the Copilot's answer format — not a
 * general markdown engine. It only ever needs to handle what the system
 * prompt asks the model for: `**Section**` headings, `- ` bullet lists,
 * inline `**bold**` / `` `code` `` spans, and plain paragraphs.
 */

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  while ((match = re.exec(text))) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(
        <strong key={`${keyPrefix}-b-${i}`} className="font-semibold text-ink">
          {token.slice(2, -2)}
        </strong>,
      );
    } else {
      nodes.push(
        <code
          key={`${keyPrefix}-c-${i}`}
          className="tnum rounded bg-surface-3 px-1 py-0.5 text-[12px] font-medium text-ink"
        >
          {token.slice(1, -1)}
        </code>,
      );
    }
    last = re.lastIndex;
    i += 1;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export function CopilotMarkdown({ text, className }: { text: string; className?: string }) {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];
  let key = 0;

  const flushBullets = () => {
    if (!bullets.length) return;
    const current = bullets;
    blocks.push(
      <ul key={`ul-${key++}`} className="my-1 list-disc space-y-1 pl-4 marker:text-ink-3">
        {current.map((b, i) => (
          <li key={i} className="text-[13px] leading-relaxed text-ink-2">
            {renderInline(b, `li-${key}-${i}`)}
          </li>
        ))}
      </ul>,
    );
    bullets = [];
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      flushBullets();
      continue;
    }
    if (line.startsWith("- ") || line.startsWith("• ")) {
      bullets.push(line.slice(2));
      continue;
    }
    flushBullets();
    const heading = /^\*\*([^*]+)\*\*:?$/.exec(line);
    if (heading) {
      blocks.push(
        <div
          key={`h-${key++}`}
          className="mt-3 text-[10.5px] font-semibold uppercase tracking-[0.09em] text-ai-text first:mt-0"
        >
          {heading[1]}
        </div>,
      );
      continue;
    }
    blocks.push(
      <p key={`p-${key++}`} className="text-[13px] leading-relaxed text-ink">
        {renderInline(line, `p-${key}`)}
      </p>,
    );
  }
  flushBullets();

  return <div className={className}>{blocks}</div>;
}
