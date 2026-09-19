"use client";

import * as React from "react";
import CodeMirror from "@uiw/react-codemirror";
import { yaml as yamlLang } from "@codemirror/lang-yaml";
import { useTheme } from "next-themes";
import { letterpressEditorTheme } from "./editorTheme";

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

  const extensions = React.useMemo(() => [yamlLang(), ...letterpressEditorTheme(dark)], [dark]);

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
      aria-label={label}
    />
  );
}
