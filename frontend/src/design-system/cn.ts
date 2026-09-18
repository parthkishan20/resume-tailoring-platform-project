/**
 * Class-name joiner. Falsy entries drop out, the rest are space-joined.
 *
 * Deliberately not `clsx` plus `tailwind-merge`: nothing here composes
 * conflicting utilities from two directions, so a 12-line helper is the whole
 * requirement and it keeps the dependency tree honest.
 */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * The focus treatment from DESIGN-SYSTEM.md section 5: 2px of `--lp-focus-ring`
 * at 2px offset, visible in both themes, never removed. `outline` rather than
 * `ring` so it needs no offset colour and therefore works on any of the four
 * paper surfaces without being told which one it is sitting on.
 */
export const focusRing =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lp-focus";

/**
 * Press feedback from the 2.7 motion table: scale(0.98) over 80ms. The
 * `data-lp-press` attribute is what `tokens.css` keys the reduced-motion
 * cancellation off, since a duration clamp alone still applies the transform.
 */
export const pressable =
  "transition-transform duration-lp-press active:scale-[0.98] motion-reduce:active:scale-100";
