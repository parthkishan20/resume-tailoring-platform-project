# ResumeTailor Design System v2 — "Letterpress"

> Status: **Approved 2026-09-18** (supersedes the 2026-07 dark + gold "tailor's thread" direction).
> Binding on every UI task in `PLAN.md` waves 1.4, 2.3, 3.1 and 3.2.
> Owner: design workstream
> Last updated: 2026-09-18

---

## 0. Design read

**Reading this as:** a single-user document workstation (structured-data editor + AI generation pipeline)
for job seekers who are comfortable with YAML, with a precise, technical-editorial language, leaning
toward owned shadcn-style components on Tailwind with one saturated accent against a paper-neutral ground.

### Scope honesty

The taste skill that produced this direction is explicitly **not** for dense product UI, data tables, or
code editors. That is most of this app. So the skill is applied as follows, and the split is deliberate:

| Surface | Treatment |
|---|---|
| Workspace shell, editor, inspector, library | Real component foundation (Radix primitives, owned shadcn-style code). Skill applied for **discipline only**: typography, palette lock, shape lock, motion motivation, state coverage, a11y, AI-tell bans. |
| CodeMirror YAML editor | Official CodeMirror theming API. No hand-rolled editor chrome. |
| Onboarding / empty state / first-run | Full skill treatment. This is the one marketing-shaped surface. |

### Dials

| Surface | `DESIGN_VARIANCE` | `MOTION_INTENSITY` | `VISUAL_DENSITY` |
|---|---|---|---|
| Workspace (editor, inspector, library) | **3** | **3** | **6** |
| Onboarding / empty state | **6** | **4** | **3** |

Reasoning: a tool you sit in for 40 minutes editing a document must be predictable, not asymmetric.
Variance is spent on the onboarding surface, where there is nothing to be productive with yet.

---

## 1. Why the current direction is being replaced

This is a rewrite, not a repaint. Each point below is a defect in the shipped UI, not a taste preference.

| # | Problem | Evidence |
|---|---|---|
| 1 | **The dark shell fights the artifact.** The product's output is a printed white page. A white PDF floating in a `#0c0d0f` shell makes the preview the highest-contrast object on screen for the wrong reason, and the user cannot judge the document's real weight against a dark ground. | `globals.css:7`, `PdfPreview.tsx` inside `bg-surface-1` |
| 2 | **Dark mode is hardcoded; the spec promised a toggle.** | `layout.tsx:20` sets `className="dark"` unconditionally; `planning/PLAN.md` "Visual Design" requires a light/dark toggle. `next-themes` is installed and unused (`package.json`). |
| 3 | **Fraunces is a banned display serif.** It is one of the two most-overused LLM display serifs, and an italic serif wordmark sits at odds with a precision tool. | `layout.tsx:6`, used at `WorkstationShell.tsx` loading state and every panel `h1` |
| 4 | **Inter as body default.** Discouraged; nothing in the brief asks for a neutral/Linear feel. | `layout.tsx:5` |
| 5 | **The gold accent sits in the banned premium-consumer palette family.** `#d9a84e` is squarely brass/ochre — the default AI reach for "craft" briefs. | `globals.css:18` |
| 6 | **Icon rail labels are 10px.** Below the readable floor, and the rail is 76px wide carrying four destinations. | `Sidebar.tsx:55` `text-[10px]`, `Sidebar.tsx:62` `w-[76px]` |
| 7 | **The job-description input is built twice.** Generate and Evaluate each own an identical 420px JD column with the same textarea, the same button shape, and diverging error styling. | `GenerationPanel.tsx:79` and `EvaluationPanel.tsx:86`, byte-identical `w-[420px] shrink-0 ... border-r` container |
| 8 | **Chat is a fourth navigation item that is not a destination.** It needs a `subtle` special case in the nav component to stop it lying about being a page. | `Sidebar.tsx:25,32,36`, where the `subtle` prop exists only to work around this |
| 9 | **Generic spinners everywhere for shaped work.** Generation has three known named stages and renders a circular spinner; the PDF preview has a known page shape and renders a circular spinner. | `GenerationPanel.tsx`, `EvaluationPanel.tsx`, `MasterResumePanel.tsx`, all via `ui/Spinner` |
| 10 | **`lucide-react` is the icon family.** Discouraged; no existing constraint forces it. | `package.json`, all panels |
| 11 | **A test selector is load-bearing on copy.** A comment in the editor header instructs future authors not to start a caption with "s" because `getByText("Resumes")` would collide. Copy is being written around fragile selectors. | `MasterResumePanel.tsx:63-65` |
| 12 | **Shape system is undeclared.** `rounded-md`, `rounded-lg`, `rounded-full` and `rounded-md` on inputs are mixed with no documented rule. | across all panels |

### What is kept

- The **split editor / preview** as the core working posture. It is correct.
- The **segmented control** for editor / split / preview. Correct control for the job.
- `prefers-reduced-motion` handling in `globals.css`. Already right, carried forward.
- Visible `:focus-visible` ring. Already right, carried forward.

---

## 2. Foundations

### 2.1 Color

One accent. Locked across every surface. Light is the default mode; dark is a full token swap, not an
afterthought.

**Direction: Ink on paper, with a cobalt thread.** Warm-neutral paper ground so the rendered PDF sits
*in* the page rather than glowing out of it; a cold saturated cobalt as the single accent so the accent
never reads as "document content". The neutral ramp is warm; the accent is cold. That tension is the
whole identity, and it is deliberately not the beige-and-brass family the previous direction used.

```css
/* tokens.css — light is the base definition */
:root {
  color-scheme: light;

  /* Paper — warm neutral ramp */
  --paper:            #faf9f7;  /* app ground */
  --paper-raised:     #ffffff;  /* cards, editor gutter, document surface */
  --paper-sunken:     #f2f1ed;  /* inspector, inset wells, code backgrounds */
  --paper-overlay:    #ffffff;  /* popovers, dialogs */

  /* Ink — text ramp, warm near-black, never #000 */
  --ink:              #1c1b19;  /* primary text */
  --ink-secondary:    #55524d;  /* labels, secondary copy */
  --ink-tertiary:     #6f6b63;  /* captions, placeholders, disabled. 5.04:1, AA */

  /* Rule — borders */
  --rule:             #e2e0da;  /* default hairline */
  --rule-strong:      #c9c6be;  /* hover, focused container, emphasis */

  /* Cobalt — the single accent */
  --accent:           #2c4ecc;  /* hsl(226 64% 49%) — saturation 64%, under the 80% cap */
  --accent-hover:     #2442b0;
  --accent-active:    #1d3795;
  --accent-contrast:  #ffffff;  /* text on accent. 6.84:1, AA */
  --accent-wash:      #eef1fc;  /* selected rows, active nav, subtle fills */
  --accent-edge:      #c3cdf4;  /* borders on accent-washed surfaces */

  /* Semantic — desaturated to sit in the neutral ramp */
  --positive:         #2f6b46;
  --positive-wash:    #e8f2ec;
  --caution:          #8a5a16;
  --caution-wash:     #fbf0e0;
  --critical:         #a3302c;
  --critical-wash:    #fbeceb;

  --focus-ring:       var(--accent);
}

:root[data-theme="dark"] {
  color-scheme: dark;

  --paper:            #16161a;  /* off-black, never #000 */
  --paper-raised:     #1e1e23;
  --paper-sunken:     #111114;
  --paper-overlay:    #26262c;

  --ink:              #eceaE6;
  --ink-secondary:    #a5a29b;
  --ink-tertiary:     #908d85;  /* 5.44:1, AA */

  --rule:             #2c2c33;
  --rule-strong:      #43434c;

  --accent:           #7d97f5;  /* lifted for contrast on dark; same hue family */
  --accent-hover:     #94a9f8;
  --accent-active:    #6b86ec;
  --accent-contrast:  #10131f;  /* 6.71:1, AA */
  --accent-wash:      #1c2138;
  --accent-edge:      #333d63;

  --positive:         #6cc48f;
  --positive-wash:    #17251d;
  --caution:          #dba459;
  --caution-wash:     #2a2015;
  --critical:         #f08c88;
  --critical-wash:    #2b1817;

  --focus-ring:       var(--accent);
}
```

**Color Consistency Lock.** Cobalt is the only accent on any surface. There is no second hue for
"AI features", no green CTA, no purple for the assistant. Semantic colors (`positive`, `caution`,
`critical`) communicate state only and never appear on a control that is not reporting state.

**The one place the accent is banned:** inside the rendered PDF preview frame. The document owns its
own color. The chrome around it does not bleed in.

**Contrast budget — MEASURED, corrected 2026-09-18.**

The ratios originally written here were estimated, not computed, and five of the eight were wrong.
One of them, `--ink-tertiary`, did not merely carry a wrong label: at 3.44:1 it **failed AA
outright**. Task 1.4 computed every pair, corrected the token that failed, and relabelled the rest.
The values below are measured. Do not edit this table without recomputing.

| Pair | Originally claimed | Measured | Standard |
|---|---|---|---|
| `--ink` on `--paper` | 14.8:1 | **16.36:1** | AAA |
| `--ink-secondary` on `--paper` | 7.2:1 | 7.39:1 | AAA |
| `--ink-tertiary` on `--paper` | 4.6:1 | **3.44:1 — FAILED** | token changed to `#6f6b63`, now **5.04:1**, AA |
| `--accent-contrast` on `--accent` | 7.1:1 | **6.84:1** | AA, not AAA |
| `--accent` on `--paper` | 6.9:1 | **6.50:1** | AA (and 6.9 was never AAA either) |
| dark `--ink` on dark `--paper` | 13.9:1 | **15.02:1** | AAA |
| dark `--ink-tertiary` on dark `--paper` | not listed | token changed to `#908d85`, **5.44:1** | AA |
| dark `--accent` on dark `--paper` | 6.4:1 | 6.55:1 | AA |
| dark `--accent-contrast` on dark `--accent` | 8.9:1 | **6.71:1** | AA. 8.9 is unreachable: pure black on `#7d97f5` tops out at 7.62:1 |

Only the two `--ink-tertiary` values were changed. Everything else keeps its specified colour and gets
an honest label, because the design intent still holds at AA and repainting the accent to chase AAA
would change the identity to satisfy a number that was invented rather than measured.

### 2.2 Typography

**Geist + Geist Mono**, self-hosted via `next/font/local` or `next/font/google`. One sans family for
everything, monospace for structured data. No display serif. Emphasis inside a heading is done with
weight or italic **of the same family**, never by swapping in a second family.

```ts
// app/fonts.ts
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
```

| Role | Spec | Used for |
|---|---|---|
| `display` | Geist 600, `clamp(1.75rem, 1.2rem + 2vw, 2.75rem)`, `tracking-[-0.03em]`, `leading-[1.1]` | Onboarding headline only |
| `title` | Geist 600, 18px, `tracking-[-0.015em]` | Panel headers |
| `heading` | Geist 600, 15px | Inspector section headings, dialog titles |
| `body` | Geist 400, 14px, `leading-[1.55]`, `max-w-[65ch]` | Prose, critiques, chat |
| `label` | Geist 500, 13px | Form labels, nav items, buttons |
| `caption` | Geist 400, 12px, `--ink-tertiary` | Timestamps, helper text, counts |
| `code` | Geist Mono 400, 13px, `leading-[1.6]` | YAML editor, keyword chips, scores, rule values |
| `numeric` | Geist Mono 500, `font-variant-numeric: tabular-nums` | Match score, counts, any aligned figure |

**Rules.**
- `caption` at 12px is the floor. Nothing renders below 12px. This kills the current 10px nav labels
  and the 11px timestamps.
- Every number the user compares or that updates in place uses `tabular-nums` so it does not jitter.
- Italic is available for emphasis. Any italic word containing `y g j p q` gets `leading-[1.1]`
  minimum plus `pb-1` reserve.

### 2.3 Shape

**Documented mixed scale.** The rule, applied everywhere without exception:

| Radius | Token | Applied to |
|---|---|---|
| 6px | `--radius-control` | Buttons, inputs, textareas, select, chips, segmented-control segments |
| 10px | `--radius-surface` | Cards, panels, dialogs, popovers, the document frame |
| 999px | `--radius-pill` | Status indicators and keyword chips **only** |
| 0 | — | Full-bleed dividers, the editor gutter, panel edges that meet a viewport edge |

### 2.4 Space and density

4px base. Workspace density is 6 out of 10: compact but not a cockpit.

| Token | Value | Use |
|---|---|---|
| `--space-1` … `--space-8` | 4, 8, 12, 16, 20, 24, 32, 48px | everything |
| Panel header height | 52px | all panel headers, uniform |
| Inspector width | 380px (resizable 320-560, persisted) | right rail |
| Nav width | 216px expanded / 56px collapsed | left rail |
| Control height | 32px default, 28px compact, 40px primary onboarding | all interactive |
| Section gap, workspace | 20px | inside inspector |
| Section gap, onboarding | 96px | between onboarding sections |

### 2.5 Elevation

Shadows are tinted to the paper hue. No pure-black shadows on light. Depth is carried mostly by
hairlines; shadow is reserved for things that genuinely float.

```css
--shadow-raised:  0 1px 2px rgb(28 27 25 / 0.05), 0 1px 1px rgb(28 27 25 / 0.03);
--shadow-overlay: 0 12px 32px -8px rgb(28 27 25 / 0.14), 0 2px 8px rgb(28 27 25 / 0.06);
--shadow-page:    0 1px 3px rgb(28 27 25 / 0.08), 0 8px 24px -12px rgb(28 27 25 / 0.12);
```

`--shadow-page` is used on exactly one element: the rendered document inside the preview frame. That
is the one object in the product that should read as a physical sheet.

### 2.6 Icons

**Phosphor** (`@phosphor-icons/react`), `weight="regular"` globally, `weight="fill"` only for an
active state that needs it. One family. `lucide-react` is removed from `package.json`.
No hand-drawn SVG paths anywhere.

### 2.7 Motion

`MOTION_INTENSITY: 3` in the workspace. Every animation below is justified in one sentence; anything
not on this list does not animate.

| Motion | Justification |
|---|---|
| Control `:active` → `scale(0.98)`, 80ms | Feedback: acknowledges the press. |
| Panel/inspector tab swap → 120ms opacity | State transition: signals the content changed without moving the layout. |
| Generation stage rail advancing | Storytelling: three named backend stages, shown as three named steps. |
| Score ring draw-in, 700ms `ease-out`, once | Hierarchy: the score is the answer; the draw pulls the eye to it. |
| Chat token stream (no animation, just append) | Feedback: the text arriving *is* the motion. |
| Skeleton shimmer, 1.4s loop, loading only | Feedback: distinguishes "loading" from "empty". |
| Toast enter/exit, 160ms translate + fade | State transition: something happened off-screen. |

Everything above collapses to instant under `prefers-reduced-motion: reduce`. No parallax, no
scroll-hijack, no magnetic hover, no marquee, no infinite loops outside the skeleton shimmer.

---

## 3. Information architecture

### 3.1 The problem being fixed

Today: an icon rail switches a single main panel between four views; two of those views independently
re-implement the same "paste a job description" column; chat is a fifth thing that pretends to be a
destination and lives in a drawer that overlays the work.

### 3.2 The new shell

Three zones. The document is always the center. The tools come to the document.

```
┌──────────┬────────────────────────────────────┬──────────────────┐
│          │  Master resume          [E|S|P] ⌄  │  Tailor          │
│  Nav     ├────────────────────────────────────┤  Evaluate        │
│  216px   │                                    │  Assistant       │
│          │   YAML editor    │   Document      ├──────────────────┤
│  Master  │                  │   ┌──────────┐  │                  │
│  Library │                  │   │          │  │  Inspector       │
│          │                  │   │  page    │  │  380px           │
│  ─────   │                  │   │          │  │  resizable       │
│  Rules   │                  │   └──────────┘  │                  │
│  Prompt  │                  │                 │                  │
│  Theme   │                  │                 │                  │
└──────────┴────────────────────────────────────┴──────────────────┘
```

**Left — Navigation (216px, collapsible to 56px, state persisted).**
Two destinations, not four:
- **Master** — the master resume document.
- **Library** — every generated resume; selecting one opens it in the center as a document.

Below a divider, three settings entries that open dialogs rather than replacing the workspace:
**Generation rules**, **Assistant prompt**, **Appearance** (light / dark / system).

Labels are always visible at 13px when expanded, and become tooltips when collapsed. No 10px text.

**Center — Document (flexible).**
Whatever is selected, rendered with the same three-mode control that already works: Editor, Split,
Preview. One component, one behaviour, whether the document is the master resume or a generated one.
This removes today's asymmetry where generated resumes get a read-only preview and only the master
gets an editor.

**Right — Inspector (380px, resizable, collapsible).**
Three tabs over one shared surface. This is where the duplicated JD column goes to become one thing:

- **Tailor** — job description input, generation rules summary with an inline edit affordance, the
  stage rail during generation, and the result handoff. Generating opens the new document in the
  center automatically.
- **Evaluate** — the same job description (shared state with Tailor, so pasting once is enough),
  scored against whatever document is currently in the center. Score, critique, keyword diff.
- **Assistant** — chat, docked rather than overlaying, so the user can watch the document change
  while the assistant edits it.

The JD lives in the inspector's own state and is shared between Tailor and Evaluate. Paste once,
generate, evaluate the result, all without retyping. That is the single biggest workflow win in the
redesign.

### 3.3 Onboarding (the one high-variance surface)

`DESIGN_VARIANCE: 6, MOTION_INTENSITY: 4, VISUAL_DENSITY: 3`.

Asymmetric split, not centered: left column carries the value proposition and the two entry paths;
right column carries a real rendered sample resume page at `--shadow-page`, which is the honest
product screenshot (it is a real PDF render, not a div mock).

Three entry paths, ranked, one primary:
1. **Drop a PDF** (primary) — the fastest path to a populated workspace.
2. **Start from the sample** — secondary.
3. **Write YAML from scratch** — tertiary text link.

Copy constraints: headline ≤ 2 lines, subtext ≤ 20 words, both CTAs above the fold, one eyebrow
maximum on the whole page, no scroll cue, no version badge, no locale strip.

---

## 4. Component inventory

Owned components, shadcn-style: the code lives in the repo, Radix provides behaviour and
accessibility. Nothing ships in default shadcn state.

### 4.1 Primitives — `src/design-system/`

| Component | Built on | Notes |
|---|---|---|
| `Button` | native | `primary` / `secondary` / `ghost` / `danger`; `sm` / `md`; icon slot; loading state that keeps its width so the layout does not jump |
| `IconButton` | native | square, tooltip required, `aria-label` required |
| `Input`, `Textarea` | native | label above, helper below, error below, never placeholder-as-label |
| `Select` | `@radix-ui/react-select` | |
| `SegmentedControl` | `@radix-ui/react-toggle-group` | replaces the hand-rolled one, keeps its current API |
| `Tabs` | `@radix-ui/react-tabs` | inspector tabs; real roving-tabindex keyboard nav |
| `Dialog` | `@radix-ui/react-dialog` | rules, prompt, appearance, destructive confirms |
| `AlertDialog` | `@radix-ui/react-alert-dialog` | replaces `ConfirmButton`, which is a two-click button pretending to be a confirmation |
| `Tooltip` | `@radix-ui/react-tooltip` | required on every icon-only control |
| `Toast` | `@radix-ui/react-toast` | transient results: saved, rendered, deleted, copied |
| `Chip` | native | keyword diff, pill radius, `positive` / `critical` / `neutral` |
| `Skeleton` | native | shape-matched; never a spinner |
| `ProgressRail` | native | named stages, determinate |
| `ScoreDial` | native SVG | evolved from the existing `ScoreRing`; tabular numerals, `role="img"` with a text label |
| `EmptyState` | native | icon, one line of what goes here, one action |
| `ErrorState` | native | message, cause when known, retry action |
| `DocumentFrame` | native | the paper sheet: `--shadow-page`, zoom, page count, download |

### 4.2 Removed

| Removed | Replaced by |
|---|---|
| `ui/Spinner` (global) | `Skeleton` for regions, inline 14px indicator inside `Button` only |
| `ui/ConfirmButton` | `AlertDialog` |
| `ChatDrawer` + `ChatPanel` split | one `Assistant` inspector tab |
| `Sidebar`'s `subtle` prop | no longer needed; chat is not a destination |
| `EmptyState` (current, onboarding-specific) | split into the onboarding route and a generic `EmptyState` primitive |

### 4.3 State coverage matrix

Every data surface ships all five. This is a checklist, not a suggestion.

| Surface | Empty | Loading | Error | Partial / streaming | Success |
|---|---|---|---|---|---|
| Master document | onboarding route | editor + page skeleton | invalid-YAML banner with line number, editor stays usable | — | rendered page |
| Library | "No tailored resumes yet" + Tailor action | 3 row skeletons | retry | — | list |
| Tailor | JD prompt | stage rail with named stage | stage-aware message, JD preserved, retry | stage rail | document opens in center |
| Evaluate | "Paste a job description" | dial + block skeletons | retry, JD preserved | — | dial, critique, chips |
| Assistant | suggested first messages | typing indicator | inline error bubble + retry | streamed tokens | message |
| Document frame | — | page-shaped skeleton | render error with the rendercv message, verbatim and copyable | — | page |

---

## 5. Accessibility contract

Non-negotiable. Each line is testable.

- **Keyboard:** every action reachable without a pointer. Inspector tabs use roving tabindex. Dialogs
  trap focus and restore it to the trigger on close. Escape closes the top layer only.
- **Focus:** 2px `--focus-ring` at 2px offset, visible in both themes, never removed. Carried forward
  from today's `globals.css`, which already gets this right.
- **Labels:** every input has a `<label>`. Every icon-only button has `aria-label` plus a tooltip.
- **Live regions:** generation stage announcements and streamed assistant tokens go to
  `aria-live="polite"`. Errors go to `aria-live="assertive"`.
- **The PDF preview:** an `<iframe>` with a real `title`, plus a visible "Download PDF" action and a
  text alternative path (view the YAML) so the document is not pointer-and-sight-only.
- **The score dial:** `role="img"` with `aria-label="Match score 72 out of 100"`. Score is never
  communicated by color alone; the numeral and a text band label ("Strong match") carry it.
- **Contrast:** every pair in 2.1 verified in both themes in CI.
- **Motion:** `prefers-reduced-motion: reduce` collapses everything in 2.7 to instant.
- **Target size:** 32px minimum for any pointer target; 40px on touch.

---

## 6. Implementation notes

- **Tailwind v4** with `@theme` mapped to the CSS variables in 2.1, so tokens are the single source
  and utilities are generated from them. No hex literal appears in a component file, ever.
- **Theme** via `next-themes` (already a dependency, currently unused), writing `data-theme` on
  `<html>`, defaulting to `system`, with the class removed from `layout.tsx:20`.
- **CodeMirror** gets two themes built from the same tokens, using the official theming API rather
  than the `!important` overrides currently in `globals.css:60-74`.
- **Fonts** through `next/font`, self-hosted. No `<link>` to Google Fonts.
- **Icons** tree-shaken per-import from Phosphor.
- **Test selectors:** every interactive element carries a stable `data-testid`. Copy is never again
  written around a text selector, and the comment at `MasterResumePanel.tsx:63` gets deleted along
  with the constraint that caused it.

---

## 7. Pre-flight check

Run before any UI work is called done. Applies to the onboarding surface in full, and to the
workspace for every box that is not marketing-page specific.

- [ ] Design read declared; dials explicit per surface
- [ ] Zero em-dash characters in any user-visible string
- [ ] One theme per page; no section inverts
- [ ] One accent (cobalt) across every surface; no second hue
- [ ] Shape scale from 2.3 applied with no exceptions
- [ ] Every CTA passes 4.5:1 against its own background
- [ ] No CTA label wraps at desktop
- [ ] Form inputs, placeholders, helper text, focus rings all pass AA
- [ ] No serif anywhere; no Fraunces, no Instrument Serif, no Inter
- [ ] Nothing renders below 12px
- [ ] Onboarding: headline ≤ 2 lines, subtext ≤ 20 words, CTAs above the fold, `pt-24` cap
- [ ] Onboarding: at most one eyebrow on the page
- [ ] No duplicate CTA intent anywhere in the product
- [ ] Every animation maps to a row in 2.7
- [ ] Reduced motion collapses all of it
- [ ] Both themes opened and checked, not just one
- [ ] All five states from 4.3 implemented for every data surface
- [ ] Skeletons are shape-matched; no circular spinner outside a button
- [ ] Icons from Phosphor only; zero hand-rolled SVG paths
- [ ] `min-h-[100dvh]`, never `h-screen`
- [ ] Every `useEffect` animation and every SSE subscription has cleanup
- [ ] No fake-precise invented numbers in any copy or sample data
- [ ] No scroll cues, version badges, locale strips, or decorative status dots

---

## 8. Open decisions

| # | Decision | Recommendation | Needs |
|---|---|---|---|
| D1 | Replace dark + gold, or keep it and fix the defects | **Decided: replace.** | Closed 2026-09-18 |
| D2 | Light as default mode | **Decided: yes**, system preference respected, manual toggle in Appearance settings | Closed 2026-09-18 |
| D3 | Tailwind v3 → v4 migration | Do it as part of this work; the token layer is being rewritten anyway | Confirm no v3-only plugin is in use |
| D4 | Radix + owned components vs. a full library | Radix primitives, owned code. The app is small enough that a full library is more constraint than leverage. | — |
| D5 | Inspector JD state shared between Tailor and Evaluate | Yes | — |
