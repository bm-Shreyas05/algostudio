import { useEffect, useId, useRef, useState, type ReactNode } from "react";

interface Props {
  /** Accessible name for the trigger; also its tooltip. */
  label: string;
  /** What the trigger shows -- usually an icon. */
  trigger: ReactNode;
  children: ReactNode;
  align?: "left" | "right";
}

/**
 * A disclosure: a button that shows and hides a panel.
 *
 * Used for the two things that do not deserve permanent space in the header
 * -- advanced settings, and help -- but must stay one click away. Closes on
 * Escape (returning focus to the trigger) and on a click anywhere outside.
 */
export function Popover({ label, trigger, children, align = "right" }: Props) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="popover-wrap" ref={wrapRef}>
      <button
        ref={buttonRef}
        type="button"
        className={`icon-btn${open ? " on" : ""}`}
        aria-label={label}
        title={label}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        {trigger}
      </button>
      {open && (
        <div id={panelId} className={`popover align-${align}`} role="group" aria-label={label}>
          {children}
        </div>
      )}
    </div>
  );
}
