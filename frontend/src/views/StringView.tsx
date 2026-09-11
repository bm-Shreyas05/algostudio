import { preview, scalarOf } from "../lib/format";
import type { ViewProps } from "./types";

/**
 * A string as an indexed row of characters.
 *
 * Strings are encoded inline rather than on the heap, so before this there was
 * no object for a view to attach to and a palindrome check or a substring
 * search drew nothing at all. The resolver synthesises a record for them; this
 * renders it, with the same pointer carets an array gets.
 */
export function StringView({ object, annotations }: ViewProps) {
  const chars = object.items ?? [];
  const pointers = annotations.filter((a) => a.kind === "pointer" && a.index !== null);
  const regions = annotations.filter((a) => a.kind === "region" && a.lo !== null);

  const inRegion = (index: number) =>
    regions.some((r) => index >= (r.lo ?? 0) && index <= (r.hi ?? -1));

  return (
    <div className="view string-view">
      <div className="string-cells">
        {chars.map((ch, index) => (
          <div
            key={index}
            className={`string-cell${inRegion(index) ? " in-region" : ""}${
              pointers.some((p) => p.index === index) ? " marked" : ""
            }`}
          >
            <span className="ch">{scalarOf(ch) === " " ? "␣" : preview(ch, 3).replace(/"/g, "")}</span>
            <span className="ix">{index}</span>
            <span className="ptrs">
              {pointers
                .filter((p) => p.index === index)
                .map((p) => (
                  <span key={p.event_id} className="pointer-tag">{p.label}</span>
                ))}
            </span>
          </div>
        ))}
        {object.trunc && <div className="string-cell truncated">…{object.n}</div>}
      </div>
    </div>
  );
}

/**
 * A frame whose locals are all numbers.
 *
 * Modular exponentiation and Euclid's GCD build no data structure at all, so
 * the canvas was empty. The values *are* the algorithm here, so show them big.
 */
export function ScalarsView({ object }: ViewProps) {
  const fields = Object.entries(object.fields ?? {});
  if (!fields.length) return <div className="view empty">no values</div>;
  return (
    <div className="view scalars-view">
      {fields.map(([name, value]) => (
        <div key={name} className="scalar-tile">
          <span className="sv">{preview(value, 14)}</span>
          <span className="sk">{name}</span>
        </div>
      ))}
    </div>
  );
}
