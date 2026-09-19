"use client";

import * as React from "react";
import CodeMirror from "@uiw/react-codemirror";
import { yaml as yamlLang } from "@codemirror/lang-yaml";
import { EditorView, ViewPlugin } from "@codemirror/view";
import { useTheme } from "next-themes";
import { letterpressEditorTheme } from "./editorTheme";

// D-88: CodeMirror's own scroll container (`.cm-scroller`) is created with
// `tabIndex = -1` (see @codemirror/view's ContentView), which axe's
// scrollable-region-focusable rule flags: the scrollable viewport has no
// keyboard path to focus and scroll it directly, independent of entering
// edit mode. There is no facet for this (EditorView.editorAttributes only
// reaches `.cm-editor`, not the scroller inside it), so a ViewPlugin patches
// the DOM node CodeMirror already created.
const scrollerFocusable = ViewPlugin.define((view) => {
  view.scrollDOM.tabIndex = 0;
  return {};
});

export interface YamlEditorProps {
  value: string;
  onChange: (next: string) => void;
  /** Announced name for the editing surface. */
  label: string;
}

/**
 * The YAML editor.
 *
 * DESIGN-SYSTEM.md 0 is explicit that the editor gets "official CodeMirror
 * theming API. No hand-rolled editor chrome", so this component is a thin
 * host: language, theme, and nothing else.
 *
 * `resolvedTheme` rather than `theme`, because `theme` is the literal
 * `"system"` when the user has not chosen, and CodeMirror needs to know which
 * of the two that resolved to. It is `undefined` until the client has read
 * storage; light is the base definition (2.1), so that is what `undefined`
 * means here.
 */
export function YamlEditor({ value, onChange, label }: YamlEditorProps) {
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";

  const extensions = React.useMemo(
    () => [
      yamlLang(),
      ...letterpressEditorTheme(dark),
      // D-88: `@uiw/react-codemirror` spreads unrecognized props (including
      // `aria-label`) onto its own outer wrapper `<div>` (the `.cm-theme-*`
      // element), not onto `.cm-content` -- the actual `role="textbox"`
      // contenteditable a screen reader lands on. `EditorView.contentAttributes`
      // is the extension point that reaches that inner element.
      EditorView.contentAttributes.of({ "aria-label": label }),
      scrollerFocusable,
    ],
    [dark, label],
  );

  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      height="100%"
      style={{ height: "100%" }}
      extensions={extensions}
      // D-87: `@uiw/react-codemirror` defaults its own `theme` prop to
      // `"light"` -- its bundled light preset, a real EditorView.theme()
      // extension with a hardcoded white background -- and applies it
      // regardless of `extensions`. Since we never passed `theme`, that
      // default stayed active permanently, underneath the CSS-variable-driven
      // theme in `extensions` that *does* follow `data-theme` correctly.
      // "none" tells the library to skip its own theme entirely: this
      // component's whole point is one token-driven theme object serving
      // both modes, not the library's own light/dark swap.
      theme="none"
      basicSetup={{ lineNumbers: true, foldGutter: false }}
    />
  );
}
