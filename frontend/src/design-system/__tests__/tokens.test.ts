import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

/**
 * The design system's non-negotiables, checked mechanically rather than by
 * eye (DESIGN-SYSTEM.md section 5 "verified in both themes in CI", and the
 * section 7 pre-flight boxes that a human reviewer cannot reliably count).
 */

const DESIGN_SYSTEM_DIR = join(__dirname, "..");
const TOKENS_CSS = readFileSync(join(DESIGN_SYSTEM_DIR, "tokens.css"), "utf8");

/** Parse one `--lp-*: value;` block, keyed by the selector that opens it. */
function tokenBlock(selector: string): Record<string, string> {
  // `${selector} {` and not just `${selector}`: the file's header comment
  // quotes both selectors, and the first match would be the prose.
  const start = TOKENS_CSS.indexOf(`${selector} {`);
  if (start === -1) throw new Error(`selector not found: ${selector}`);
  const open = TOKENS_CSS.indexOf("{", start);
  const close = TOKENS_CSS.indexOf("\n}", open);
  const body = TOKENS_CSS.slice(open, close);
  const out: Record<string, string> = {};
  for (const match of body.matchAll(/(--lp-[a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    out[match[1]] = match[2].trim();
  }
  return out;
}

const light = tokenBlock(':root,\n[data-theme="light"]');
const dark = { ...light, ...tokenBlock('[data-theme="dark"]') };

function relativeLuminance(hex: string): number {
  const value = hex.replace("#", "");
  const channels = [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(foreground: string, background: string): number {
  const a = relativeLuminance(foreground);
  const b = relativeLuminance(background);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

const THEMES: Array<[string, Record<string, string>]> = [
  ["light", light],
  ["dark", dark],
];

describe("tokens", () => {
  it("defines the same token names in both themes", () => {
    const lightNames = Object.keys(light).filter((n) => !n.startsWith("--lp-space"));
    const darkOnly = tokenBlock('[data-theme="dark"]');
    for (const name of Object.keys(darkOnly)) {
      expect(lightNames).toContain(name);
    }
  });

  // Section 7: "Nothing renders below 12px."
  it("has no type token below the 12px floor", () => {
    const sizes = Object.entries(light)
      .filter(([name]) => name.startsWith("--lp-text-"))
      .map(([name, value]) => [name, value] as const)
      .filter(([, value]) => value.endsWith("px"));
    expect(sizes.length).toBeGreaterThan(0);
    for (const [name, value] of sizes) {
      expect(Number.parseFloat(value)).toBeGreaterThanOrEqual(12);
      expect(name).toBeTruthy();
    }
  });

  // Section 5: "Target size: 32px minimum for any pointer target."
  it("keeps the default control height at the 32px target minimum", () => {
    expect(Number.parseFloat(light["--lp-control-h"])).toBeGreaterThanOrEqual(32);
  });
});

describe.each(THEMES)("contrast in %s", (themeName, t) => {
  const grounds = ["--lp-paper", "--lp-paper-raised", "--lp-paper-sunken", "--lp-paper-overlay"];

  // AAA body text on every paper surface it can land on.
  it.each(grounds)(`--lp-ink on %s clears 7:1`, (ground) => {
    expect(contrast(t["--lp-ink"], t[ground])).toBeGreaterThanOrEqual(7);
  });

  // AA for secondary copy and for the tertiary ramp, which section 7 requires
  // to cover placeholders and helper text. The spec's own tertiary value did
  // not clear this; see the 1.4 report.
  it.each(grounds)(`--lp-ink-secondary on %s clears AA`, (ground) => {
    expect(contrast(t["--lp-ink-secondary"], t[ground])).toBeGreaterThanOrEqual(4.5);
  });

  it.each(grounds)(`--lp-ink-tertiary on %s clears AA`, (ground) => {
    expect(contrast(t["--lp-ink-tertiary"], t[ground])).toBeGreaterThanOrEqual(4.5);
  });

  // Section 7: "Every CTA passes 4.5:1 against its own background."
  it.each(["--lp-accent", "--lp-accent-hover", "--lp-accent-active", "--lp-critical"])(
    "--lp-accent-contrast on %s clears AA",
    (fill) => {
      expect(contrast(t["--lp-accent-contrast"], t[fill])).toBeGreaterThanOrEqual(4.5);
    },
  );

  it.each(grounds)("--lp-accent as link text on %s clears AA", (ground) => {
    expect(contrast(t["--lp-accent"], t[ground])).toBeGreaterThanOrEqual(4.5);
  });

  it.each(["positive", "caution", "critical"])(
    "--lp-%s clears AA on its own wash and on paper",
    (name) => {
      expect(contrast(t[`--lp-${name}`], t[`--lp-${name}-wash`])).toBeGreaterThanOrEqual(4.5);
      expect(contrast(t[`--lp-${name}`], t["--lp-paper"])).toBeGreaterThanOrEqual(4.5);
    },
  );

  // WCAG 1.4.11: a control identified only by its boundary needs 3:1.
  it.each(grounds)("--lp-rule-control clears 3:1 on %s", (ground) => {
    expect(contrast(t["--lp-rule-control"], t[ground])).toBeGreaterThanOrEqual(3);
  });

  // The focus ring has to be visible in both themes (section 5).
  it.each(grounds)("the focus ring clears 3:1 on %s", (ground) => {
    expect(contrast(t["--lp-accent"], t[ground])).toBeGreaterThanOrEqual(3);
    expect(themeName).toBeTruthy();
  });
});

describe("source hygiene", () => {
  const sourceFiles = readdirSync(DESIGN_SYSTEM_DIR)
    .filter((f) => f.endsWith(".tsx") || f.endsWith(".ts"))
    .filter((f) => !f.endsWith(".test.tsx") && f !== "test-polyfills.ts")
    .map((f) => [f, readFileSync(join(DESIGN_SYSTEM_DIR, f), "utf8")] as const);

  /** Comments may name a banned construct in order to ban it. Code may not. */
  const codeOnly = (source: string) =>
    source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

  it("finds the primitives", () => {
    expect(sourceFiles.length).toBeGreaterThanOrEqual(14);
  });

  // Section 7: "Zero em-dash characters in any user-visible string."
  it.each(sourceFiles)("%s contains no em dash", (_name, source) => {
    expect(source).not.toMatch(/\u2014/);
  });

  // Section 6: "No hex literal appears in a component file, ever."
  it.each(sourceFiles)("%s contains no colour literal", (_name, source) => {
    expect(source).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(source).not.toMatch(/\brgba?\(/);
    expect(source).not.toMatch(/\bhsla?\(/);
  });

  // Section 2.6: "No hand-drawn SVG paths anywhere."
  it.each(sourceFiles)("%s draws no SVG of its own", (_name, source) => {
    expect(codeOnly(source)).not.toMatch(/<svg/);
    expect(codeOnly(source)).not.toMatch(/<path/);
  });

  // Section 2.2: 12px is the floor, so no smaller arbitrary size may appear.
  it.each(sourceFiles)("%s renders nothing below 12px", (_name, source) => {
    for (const match of source.matchAll(/text-\[(\d+(?:\.\d+)?)px\]/g)) {
      expect(Number.parseFloat(match[1])).toBeGreaterThanOrEqual(12);
    }
  });
});
