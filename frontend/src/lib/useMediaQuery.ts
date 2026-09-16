import { useEffect, useState } from "react";

/**
 * Subscribe to a CSS media query from React.
 *
 * The studio is a four-panel IDE built around dragging dividers, and dragging
 * a divider is not a gesture a phone has. Rather than shrink the desktop
 * layout until it is merely bad, the app switches to one pane at a time below
 * this breakpoint -- so the query has to be readable during render, not only
 * in CSS.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia(query).matches
      : false,
  );

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const list = window.matchMedia(query);
    const onChange = (event: MediaQueryListEvent) => setMatches(event.matches);
    setMatches(list.matches);
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** The width below which the split layout stops being usable. */
export const MOBILE_QUERY = "(max-width: 900px)";
