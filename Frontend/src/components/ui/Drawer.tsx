import { useEffect, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { IconButton } from "./Button";

export function Drawer({
  open,
  onClose,
  title,
  subtitle,
  headerAccessory,
  footer,
  width = 620,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  headerAccessory?: ReactNode;
  footer?: ReactNode;
  width?: number;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <motion.div
            className="absolute inset-0 bg-[#0b0f16]/35 backdrop-blur-[1px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
          />
          <motion.aside
            role="dialog"
            aria-modal="true"
            className="relative flex h-full w-full flex-col border-l border-line bg-surface shadow-lg"
            style={{ maxWidth: width }}
            initial={{ x: 32, opacity: 0.4 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 24, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
          >
            <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
              <div className="min-w-0">
                <div className="flex items-center gap-3">
                  <h2 className="truncate text-[17px] font-semibold tracking-[-0.02em] text-ink">{title}</h2>
                  {headerAccessory}
                </div>
                {subtitle && <div className="mt-1.5 text-[13px] text-ink-2">{subtitle}</div>}
              </div>
              <IconButton label="Close panel" onClick={onClose} className="-mr-1.5 -mt-1">
                <X className="size-4.5" />
              </IconButton>
            </header>

            <div className="thin-scroll flex-1 overflow-y-auto">{children}</div>

            {footer && (
              <footer className="flex items-center justify-between gap-3 border-t border-line bg-surface-2 px-6 py-4">
                {footer}
              </footer>
            )}
          </motion.aside>
        </div>
      )}
    </AnimatePresence>
  );
}
