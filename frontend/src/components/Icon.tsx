/**
 * The app's icons, as inline SVG.
 *
 * These replace Unicode glyphs (⟲ ⤴ ◀ ▶ ⤵ ↘ ⇥), which render from whatever
 * font the OS substitutes -- different sizes, weights and baselines on Windows,
 * macOS and Android, and occasionally as an emoji. A transport bar whose
 * buttons change shape per machine looks broken, so the shapes are drawn here.
 *
 * Every icon is decorative (aria-hidden): the button that holds it carries the
 * accessible name. An icon is never the only way to know what a control does.
 */

const PATHS = {
  restart: "M4 10a6 6 0 1 0 1.8-4.3M4 3.5V6.5h3",
  back: "M12.5 4.5 7 10l5.5 5.5",
  forward: "M7.5 4.5 13 10l-5.5 5.5",
  end: "M5.5 4.5 11 10l-5.5 5.5M14.5 4.5v11",
  into: "M10 3.5v9M6 9l4 4 4-4M5 16.5h10",
  over: "M4 12.5a6 6 0 0 1 11.2-3M15.5 5v4.5H11",
  out: "M10 16.5v-9M6 11l4-4 4 4M5 3.5h10",
  library: "M4 4.5h3v11H4zM8.5 4.5h3v11h-3zM13.2 5.1l2.8-.8 2.6 9.9-2.8.8z",
  code: "M7.5 6 3.5 10l4 4M12.5 6l4 4-4 4",
  settings:
    "M10 12.8a2.8 2.8 0 1 0 0-5.6 2.8 2.8 0 0 0 0 5.6ZM16.2 11.3l1.3.8-1.4 2.4-1.5-.4a5.8 5.8 0 0 1-1.6.9L12.6 16.5h-2.8l-.4-1.5a5.8 5.8 0 0 1-1.6-.9l-1.5.4-1.4-2.4 1.3-.8a5.6 5.6 0 0 1 0-1.8L4.9 8.7l1.4-2.4 1.5.4a5.8 5.8 0 0 1 1.6-.9l.4-1.3h2.8l.4 1.3a5.8 5.8 0 0 1 1.6.9l1.5-.4 1.4 2.4-1.3.8a5.6 5.6 0 0 1 0 1.8Z",
  help: "M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM7.8 7.9a2.3 2.3 0 0 1 4.4.9c0 1.5-2.2 1.8-2.2 3.2M10 14.2v.1",
  search: "M8.5 14a5.5 5.5 0 1 0 0-11 5.5 5.5 0 0 0 0 11ZM13 13l4 4",
  chevron: "M5.5 8 10 12.5 14.5 8",
  lock: "M6 9V7a4 4 0 0 1 8 0v2M5 9h10v8H5z",
  // A staircase: how far each step moves. Not the gear, which is Settings.
  steps: "M3 16h4v-4h4V8h4V4h2",
} as const;

export type IconName = keyof typeof PATHS | "play" | "pause";

export function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  // Play and pause are filled shapes; everything else is a 1.8px stroke.
  if (name === "play") {
    return (
      <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden="true" className="icon">
        <path d="M6 4.2v11.6L15.8 10z" fill="currentColor" />
      </svg>
    );
  }
  if (name === "pause") {
    return (
      <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden="true" className="icon">
        <rect x="5" y="4.5" width="3.4" height="11" rx="1" fill="currentColor" />
        <rect x="11.6" y="4.5" width="3.4" height="11" rx="1" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden="true" className="icon">
      <path
        d={PATHS[name]}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
