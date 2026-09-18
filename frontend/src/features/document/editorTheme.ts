import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import type { Extension } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { tags } from "@lezer/highlight";

/**
 * CodeMirror theming through CodeMirror's own API, which is what
 * DESIGN-SYSTEM.md section 6 asks for: "CodeMirror gets two themes built from
 * the same tokens, using the official theming API rather than the `!important`
 * overrides currently in `globals.css`". Those overrides are gone; this file
 * replaces them.
 *
 * Every colour is a `var(--lp-*)` reference rather than a value, so one theme
 * object serves both light and dark and the editor follows `data-theme`
 * without being re-created. The `dark` flag still has to be passed, because
 * CodeMirror uses it for the parts it computes itself (the native selection
 * layer and the caret's own contrast handling) rather than for colour lookup.
 */

function chrome(dark: boolean): Extension {
  return EditorView.theme(
    {
      "&": {
        backgroundColor: "var(--lp-paper-raised)",
        color: "var(--lp-ink)",
        height: "100%",
        // 2.2 `code`: Geist Mono 13px at 1.6.
        fontFamily: "var(--font-geist-mono), ui-monospace, SFMono-Regular, monospace",
        fontSize: "var(--lp-text-code)",
      },
      ".cm-scroller": {
        fontFamily: "inherit",
        lineHeight: "var(--lp-leading-code)",
      },
      ".cm-content": {
        caretColor: "var(--lp-accent)",
      },
      // 2.3: the editor gutter is one of the two surfaces that take radius 0.
      ".cm-gutters": {
        backgroundColor: "var(--lp-paper-raised)",
        color: "var(--lp-ink-tertiary)",
        border: "none",
        borderRight: "1px solid var(--lp-rule)",
        borderRadius: "0",
      },
      ".cm-activeLine": {
        backgroundColor: "var(--lp-paper-sunken)",
      },
      ".cm-activeLineGutter": {
        backgroundColor: "var(--lp-paper-sunken)",
        color: "var(--lp-ink-secondary)",
      },
      ".cm-lineNumbers .cm-gutterElement": {
        // Tabular by construction: a gutter whose digits shift width makes the
        // whole document jitter on the hundredth line (2.2).
        fontVariantNumeric: "tabular-nums",
      },
      "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, ::selection": {
        backgroundColor: "var(--lp-accent-wash)",
      },
      ".cm-selectionBackground": {
        backgroundColor: "var(--lp-accent-wash)",
      },
      ".cm-cursor, .cm-dropCursor": {
        borderLeftColor: "var(--lp-accent)",
      },
      // The editor sits inside a pane that already draws its own focus
      // treatment, and CodeMirror's default is a 1px outline that reads as a
      // second border against the hairline.
      "&.cm-editor.cm-focused": {
        outline: "none",
      },
      ".cm-matchingBracket, .cm-nonmatchingBracket": {
        backgroundColor: "var(--lp-accent-wash)",
        color: "inherit",
      },
    },
    { dark },
  );
}

/**
 * YAML highlighting on the neutral ramp plus the one accent.
 *
 * Structured data is not prose: the useful distinction is key from value from
 * comment, and three steps of the ink ramp carry it without introducing the
 * second and third hues a conventional syntax palette would. That keeps the
 * 2.1 colour lock intact inside the editor, which is the largest single
 * surface in the product.
 */
const highlight = HighlightStyle.define([
  { tag: [tags.propertyName, tags.definition(tags.propertyName)], color: "var(--lp-accent)" },
  { tag: [tags.keyword, tags.atom, tags.bool], color: "var(--lp-accent)", fontWeight: "500" },
  { tag: [tags.string, tags.special(tags.string)], color: "var(--lp-ink)" },
  { tag: [tags.number], color: "var(--lp-ink)", fontVariantNumeric: "tabular-nums" },
  { tag: [tags.comment, tags.lineComment, tags.blockComment], color: "var(--lp-ink-tertiary)" },
  { tag: [tags.meta, tags.punctuation, tags.separator], color: "var(--lp-ink-secondary)" },
  { tag: [tags.invalid], color: "var(--lp-critical)" },
]);

/** The full extension set. Memoise on `dark` at the call site. */
export function letterpressEditorTheme(dark: boolean): Extension[] {
  return [chrome(dark), syntaxHighlighting(highlight)];
}
