import { preview, scalarOf } from "../lib/format";
import { MARK_COLORS, type ViewProps } from "./types";

/**
 * Indexed cells with an index ruler, pointer carets and region shading.
 *
 * Everything it draws comes from the object's contents plus the annotations
 * targeting it. It has no idea which algorithm produced them.
 */
export function ArrayView({ object, annotations }: ViewProps) {
  const items = object.items ?? [];
  const numbers = items.map(scalarOf).filter((v) => typeof v === "number") as number[];
  const numeric = numbers.length === items.length && items.length > 0;
  const max = numeric ? Math.max(...numbers.map(Math.abs), 1) : 1;

  const pointers = annotations.filter((a) => a.kind === "pointer" && a.index !== null);
  const regions = annotations.filter((a) => a.kind === "region" && a.lo !== null);
  const flashes = new Map<number, string>();
  for (const a of annotations) {
    const color = MARK_COLORS[a.kind];
    if (!color) continue;
    for (const key of ["i", "j", "index"] as const) {
      const raw = a.kind === "region" ? null : (a.value?.[key] ?? (key === "index" ? a.index : null));
      if (typeof raw === "number") flashes.set(raw, color);
    }
  }

  const inRegion = (index: number) =>
    regions.some((r) => index >= (r.lo ?? 0) && index <= (r.hi ?? -1));

  // Short lists get room to breathe; long ones stay compact enough to scan.
  const size = items.length <= 12 ? " size-l" : items.length <= 24 ? " size-m" : "";

  return (
    <div className={`view array-view${size}`}>
      <div className="array-cells">
        {items.map((value, index) => {
          const flash = flashes.get(index);
          // A fraction of the bar's maximum height, which the CSS sets per size.
          const height = numeric
            ? `max(4px, calc(var(--bar-max) * ${(Math.abs(numbers[index]) / max).toFixed(3)}))`
            : 0;
          return (
            <div
              key={index}
              className={`array-cell${inRegion(index) ? " in-region" : ""}`}
              style={flash ? { borderColor: flash, boxShadow: `0 0 0 2px ${flash}55` } : undefined}
            >
              {numeric && (
                <div className="array-bar" style={{ height, background: flash ?? "var(--bar)" }} />
              )}
              <div className="array-value">{preview(value, 10)}</div>
              <div className="array-index">{index}</div>
              <div className="array-pointers">
                {pointers
                  .filter((p) => p.index === index)
                  .map((p) => (
                    <span key={p.event_id} className="pointer-tag" title={`pointer ${p.label}`}>
                      {p.label}
                    </span>
                  ))}
              </div>
            </div>
          );
        })}
        {object.trunc && <div className="array-cell truncated">…{object.n} total</div>}
      </div>
      {regions.length > 0 && (
        <div className="region-legend">
          {regions.map((r) => (
            <span key={r.event_id}>
              {r.label} [{r.lo}..{r.hi}]
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
