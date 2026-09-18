"use client";

import * as React from "react";
import {
  ArrowClockwise,
  DownloadSimple,
  FileText,
  MagnifyingGlass,
  Sparkle,
  Trash,
} from "@phosphor-icons/react";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogTrigger,
  Button,
  Chip,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogTrigger,
  EmptyState,
  ErrorState,
  IconButton,
  Input,
  ProgressRail,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  ToastHost,
  Tooltip,
  useToast,
} from "@/design-system";

/* -------------------------------------------------------------------------
 * Layout helpers, local to the preview. These are scaffolding for the
 * gallery, not part of the design system.
 * ---------------------------------------------------------------------- */

function Section({
  id,
  title,
  note,
  children,
}: {
  id: string;
  title: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="flex flex-col gap-lp-4 border-t border-lp-rule pt-lp-6">
      <div className="flex flex-col gap-lp-1">
        <h2 className="text-lp-title font-semibold text-lp-ink">{title}</h2>
        {note ? <p className="max-w-[65ch] text-lp-caption text-lp-ink-tertiary">{note}</p> : null}
      </div>
      {children}
    </section>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-lp-3">
      <span className="w-[112px] shrink-0 font-lp-mono text-lp-caption text-lp-ink-tertiary">
        {label}
      </span>
      {children}
    </div>
  );
}

function Swatch({ name, token }: { name: string; token: string }) {
  return (
    <div className="flex items-center gap-lp-2">
      <span
        aria-hidden="true"
        className="h-lp-7 w-lp-7 shrink-0 rounded-lp-control border border-lp-rule-control"
        style={{ background: `var(${token})` }}
      />
      <span className="font-lp-mono text-lp-caption text-lp-ink-secondary">{name}</span>
    </div>
  );
}

const PAPER_TOKENS = ["--lp-paper", "--lp-paper-raised", "--lp-paper-sunken", "--lp-paper-overlay"];
const INK_TOKENS = ["--lp-ink", "--lp-ink-secondary", "--lp-ink-tertiary"];
const RULE_TOKENS = ["--lp-rule", "--lp-rule-strong", "--lp-rule-control"];
const ACCENT_TOKENS = [
  "--lp-accent",
  "--lp-accent-hover",
  "--lp-accent-active",
  "--lp-accent-contrast",
  "--lp-accent-wash",
  "--lp-accent-edge",
];
const SEMANTIC_TOKENS = [
  "--lp-positive",
  "--lp-positive-wash",
  "--lp-caution",
  "--lp-caution-wash",
  "--lp-critical",
  "--lp-critical-wash",
];

const GENERATION_STAGES = [
  { id: "read", label: "Reading the job description" },
  { id: "tailor", label: "Tailoring the resume" },
  { id: "render", label: "Rendering the PDF" },
];

/* ------------------------------------------------------------------------- */

function ToastDemo() {
  const { toast } = useToast();
  return (
    <Row label="toast">
      <Button
        onClick={() => {
          toast({ title: "Resume saved", description: "Master resume, just now." });
        }}
      >
        Neutral
      </Button>
      <Button
        variant="primary"
        onClick={() => {
          toast({ title: "PDF rendered", description: "2 pages.", tone: "positive" });
        }}
      >
        Positive
      </Button>
      <Button
        variant="danger"
        onClick={() => {
          toast({
            title: "Render failed",
            description: "See the editor for details.",
            tone: "critical",
          });
        }}
      >
        Critical
      </Button>
    </Row>
  );
}

/**
 * Every primitive in every state. `Gallery` is rendered twice by the page,
 * once pinned light and once pinned dark, so a reviewer sees both themes at
 * the same time rather than toggling and trusting memory.
 */
export function Gallery({ scope }: { scope: string }) {
  const [railIndex, setRailIndex] = React.useState(1);

  return (
    <ToastHost>
      <div className="flex flex-col gap-lp-7">
        <Section
          id={`${scope}-color`}
          title="Color"
          note="One accent. Light is the base; dark is a full token swap."
        >
          <div className="grid gap-lp-3 sm:grid-cols-2 lg:grid-cols-3">
            {[
              ["Paper", PAPER_TOKENS],
              ["Ink", INK_TOKENS],
              ["Rule", RULE_TOKENS],
              ["Cobalt", ACCENT_TOKENS],
              ["Semantic", SEMANTIC_TOKENS],
            ].map(([group, tokens]) => (
              <div
                key={group as string}
                className="flex flex-col gap-lp-2 rounded-lp-surface border border-lp-rule bg-lp-paper-raised p-lp-4"
              >
                <p className="text-lp-label font-medium text-lp-ink">{group as string}</p>
                {(tokens as string[]).map((token) => (
                  <Swatch key={token} name={token} token={token} />
                ))}
              </div>
            ))}
          </div>
        </Section>

        <Section
          id={`${scope}-type`}
          title="Type"
          note="Geist and Geist Mono. One family, no display serif. 12px is the floor."
        >
          <div className="flex flex-col gap-lp-3 rounded-lp-surface border border-lp-rule bg-lp-paper-raised p-lp-5">
            <p className="text-lp-display font-semibold text-lp-ink">Display, onboarding only</p>
            <p className="text-lp-title font-semibold text-lp-ink">Title, panel headers</p>
            <p className="text-lp-heading font-semibold text-lp-ink">Heading, inspector sections</p>
            <p className="max-w-[65ch] text-lp-body text-lp-ink">
              Body copy at 14px with 1.55 leading, capped at 65 characters so a line stays readable.
              Emphasis inside a heading is done with{" "}
              <em className="not-italic font-semibold">weight</em> or{" "}
              <em className="leading-[1.1] pb-1 inline-block">an italic of the same family</em>,
              never a second family.
            </p>
            <p className="text-lp-label font-medium text-lp-ink">Label, forms and nav</p>
            <p className="text-lp-caption text-lp-ink-tertiary">Caption, 12px, the floor</p>
            <p className="font-lp-mono text-lp-code text-lp-ink-secondary">
              code: yaml, keyword chips
            </p>
            <p className="font-lp-mono text-lp-body font-medium tabular-nums text-lp-ink">
              numeric 72 / 100, tabular so it does not jitter
            </p>
          </div>
        </Section>

        <Section
          id={`${scope}-shape`}
          title="Shape and elevation"
          note="Three radii, three shadows."
        >
          <div className="flex flex-wrap gap-lp-4">
            <div className="flex h-lp-8 w-[140px] items-center justify-center rounded-lp-control border border-lp-rule bg-lp-paper-raised font-lp-mono text-lp-caption text-lp-ink-secondary">
              control 6px
            </div>
            <div className="flex h-lp-8 w-[140px] items-center justify-center rounded-lp-surface border border-lp-rule bg-lp-paper-raised font-lp-mono text-lp-caption text-lp-ink-secondary">
              surface 10px
            </div>
            <div className="flex h-lp-8 w-[140px] items-center justify-center rounded-lp-pill border border-lp-rule bg-lp-paper-raised font-lp-mono text-lp-caption text-lp-ink-secondary">
              pill 999px
            </div>
          </div>
          <div className="flex flex-wrap gap-lp-4">
            <div className="flex h-lp-8 w-[140px] items-center justify-center rounded-lp-surface bg-lp-paper-raised shadow-lp-raised font-lp-mono text-lp-caption text-lp-ink-secondary">
              raised
            </div>
            <div className="flex h-lp-8 w-[140px] items-center justify-center rounded-lp-surface bg-lp-paper-raised shadow-lp-overlay font-lp-mono text-lp-caption text-lp-ink-secondary">
              overlay
            </div>
            <div className="flex h-lp-8 w-[140px] items-center justify-center rounded-lp-surface bg-lp-paper-raised shadow-lp-page font-lp-mono text-lp-caption text-lp-ink-secondary">
              page
            </div>
          </div>
        </Section>

        <Section
          id={`${scope}-button`}
          title="Button"
          note="Four variants, two sizes, five states each."
        >
          {(["primary", "secondary", "ghost", "danger"] as const).map((variant) => (
            <Row key={variant} label={variant}>
              <Button variant={variant} size="md">
                Default
              </Button>
              <Button variant={variant} size="md" icon={<Sparkle size={14} />}>
                With icon
              </Button>
              <Button variant={variant} size="md" loading loadingLabel="Generating">
                Generate
              </Button>
              <Button variant={variant} size="md" disabled>
                Disabled
              </Button>
              <Button variant={variant} size="sm">
                Small
              </Button>
            </Row>
          ))}
          <Row label="icon only">
            <IconButton label="Download PDF" icon={<DownloadSimple size={16} />} />
            <IconButton label="Search" icon={<MagnifyingGlass size={16} />} variant="secondary" />
            <IconButton label="Re-render" icon={<ArrowClockwise size={16} />} variant="primary" />
            <IconButton label="Delete resume" icon={<Trash size={16} />} variant="danger" />
            <IconButton label="Compact" icon={<Sparkle size={14} />} size="sm" />
            <IconButton label="Disabled action" icon={<Trash size={16} />} disabled />
          </Row>
          <Row label="tooltip">
            <Tooltip label="Tooltips carry the label for pointer users">
              <Button variant="secondary">Hover or focus me</Button>
            </Tooltip>
          </Row>
        </Section>

        <Section
          id={`${scope}-fields`}
          title="Input and Textarea"
          note="Label above, helper or error below. The placeholder never carries the label."
        >
          <div className="grid gap-lp-4 md:grid-cols-2">
            <Input label="Resume name" placeholder="Senior backend engineer" />
            <Input label="Resume name" defaultValue="Draft 3" helper="Shown in the library list." />
            <Input label="Resume name" defaultValue="" error="Enter a name before saving." />
            <Input
              label="Resume name"
              defaultValue="Locked"
              disabled
              helper="Read only while rendering."
            />
            <Textarea
              label="Job description"
              rows={4}
              placeholder="Paste the posting here."
              helper="Pasted once, used by both Tailor and Evaluate."
            />
            <Textarea
              label="Job description"
              rows={4}
              defaultValue=""
              error="Paste a job description to continue."
            />
          </div>
        </Section>

        <Section
          id={`${scope}-tabs`}
          title="Tabs"
          note="Radix roving tabindex. Arrow keys move, Home and End jump."
        >
          <Tabs
            defaultValue="tailor"
            className="rounded-lp-surface border border-lp-rule bg-lp-paper-raised"
          >
            <TabsList>
              <TabsTrigger value="tailor">Tailor</TabsTrigger>
              <TabsTrigger value="evaluate">Evaluate</TabsTrigger>
              <TabsTrigger value="assistant">Assistant</TabsTrigger>
              <TabsTrigger value="locked" disabled>
                Disabled
              </TabsTrigger>
            </TabsList>
            <TabsContent value="tailor">Job description, rules, and the stage rail.</TabsContent>
            <TabsContent value="evaluate">Score, critique, keyword diff.</TabsContent>
            <TabsContent value="assistant">Chat, docked beside the document.</TabsContent>
            <TabsContent value="locked">Not reachable.</TabsContent>
          </Tabs>
        </Section>

        <Section
          id={`${scope}-overlays`}
          title="Dialog, AlertDialog, Toast"
          note="Focus is trapped and restored. Escape closes the top layer only."
        >
          <Row label="dialog">
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="secondary">Generation rules</Button>
              </DialogTrigger>
              <DialogContent
                title="Generation rules"
                description="Applied to every tailored resume."
              >
                <Textarea
                  label="Rules"
                  rows={5}
                  defaultValue={"Keep bullets under 2 lines.\nLead with impact."}
                />
                <DialogFooter>
                  <Button variant="ghost">Cancel</Button>
                  <Button variant="primary">Save rules</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </Row>
          <Row label="alert">
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="danger" icon={<Trash size={14} />}>
                  Delete resume
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent
                title="Delete this resume?"
                description="The resume and its rendered PDF are removed. This cannot be undone."
                confirmLabel="Delete"
                onConfirm={() => undefined}
              />
            </AlertDialog>
          </Row>
          <ToastDemo />
        </Section>

        <Section
          id={`${scope}-chip`}
          title="Chip"
          note="Pill radius, one of only two things 2.3 permits it on."
        >
          <Row label="tones">
            <Chip tone="positive" toneLabel="Matched">
              kubernetes
            </Chip>
            <Chip tone="critical" toneLabel="Missing">
              terraform
            </Chip>
            <Chip tone="neutral">python</Chip>
          </Row>
        </Section>

        <Section
          id={`${scope}-loading`}
          title="Skeleton"
          note="Shape matched. No circular spinner outside a button."
        >
          <div className="grid gap-lp-5 md:grid-cols-2">
            <div className="flex flex-col gap-lp-2">
              <Skeleton shape="text" className="w-1/3" />
              <Skeleton shape="text" className="w-full" />
              <Skeleton shape="text" className="w-4/5" />
              <Skeleton shape="block" className="h-lp-8 w-full" />
            </div>
            <Skeleton shape="page" />
          </div>
        </Section>

        <Section
          id={`${scope}-rail`}
          title="ProgressRail"
          note="Three named backend stages, determinate, announced politely."
        >
          <Row label="stage">
            <Button size="sm" onClick={() => setRailIndex((i) => Math.max(0, i - 1))}>
              Back
            </Button>
            <Button size="sm" onClick={() => setRailIndex((i) => Math.min(2, i + 1))}>
              Forward
            </Button>
          </Row>
          <div className="grid gap-lp-5 md:grid-cols-3">
            <ProgressRail stages={GENERATION_STAGES} currentIndex={railIndex} label="Generation" />
            <ProgressRail
              stages={GENERATION_STAGES}
              currentIndex={1}
              status="error"
              errorMessage="The tailoring step failed. Your job description was kept."
              label="Generation"
            />
            <ProgressRail
              stages={GENERATION_STAGES}
              currentIndex={2}
              status="complete"
              label="Generation"
            />
          </div>
        </Section>

        <Section
          id={`${scope}-states`}
          title="EmptyState and ErrorState"
          note="Two of the five states every data surface ships."
        >
          <div className="grid gap-lp-5 md:grid-cols-2">
            <EmptyState
              icon={<FileText size={28} />}
              title="No tailored resumes yet"
              description="Paste a job description in Tailor and the result lands here."
              action={<Button variant="primary">Open Tailor</Button>}
            />
            <ErrorState
              title="The renderer could not build this PDF"
              cause={"rendercv: invalid date '2023-13' in section 'experience', entry 2"}
              action={
                <Button variant="secondary" icon={<ArrowClockwise size={14} />}>
                  Try again
                </Button>
              }
            />
          </div>
        </Section>
      </div>
    </ToastHost>
  );
}
