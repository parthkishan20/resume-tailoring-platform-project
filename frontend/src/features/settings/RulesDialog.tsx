"use client";

import * as React from "react";
import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  ErrorState,
  Input,
  Skeleton,
  useToast,
} from "@/design-system";
import { useResetRules, useRules, useUpdateRules } from "@/features/queries";
import type { Rule } from "@/lib/types";

const humanize = (value: string) => value.replace(/_/g, " ");
const ruleId = (rule: Rule) => `${rule.section}.${rule.rule_key}`;

/**
 * Generation rules, as a dialog rather than a disclosure buried in a panel
 * (DESIGN-SYSTEM.md 3.2: settings entries "open dialogs rather than replacing
 * the workspace").
 *
 * Three defects from the audit close by moving here rather than by being
 * fixed:
 *
 * - P2-31, unlabelled inputs. Every field is an `Input`, which cannot render
 *   without a `<label>`.
 * - P2-28, rules editing fails silently. The old panel saved on blur and
 *   swallowed the error, so a rejected value stayed on screen looking saved.
 *   This form saves on submit, reports failure, and keeps the user's values.
 * - The state desync in the same finding. Values come from the query cache, so
 *   a save that does not round-trip cannot leave two sources disagreeing.
 */
export function RulesDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const rules = useRules();
  const update = useUpdateRules();
  const reset = useResetRules();
  const { toast } = useToast();

  const [draft, setDraft] = React.useState<Record<string, string>>({});

  // Adopt server values whenever the dialog opens, so a cancelled edit does
  // not persist into the next visit.
  React.useEffect(() => {
    if (!open || !rules.data) return;
    setDraft(Object.fromEntries(rules.data.map((rule) => [ruleId(rule), rule.rule_value])));
  }, [open, rules.data]);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!rules.data) return;
    const payload: Rule[] = rules.data.map((rule) => ({
      section: rule.section,
      rule_key: rule.rule_key,
      rule_value: draft[ruleId(rule)] ?? rule.rule_value,
    }));
    update.mutate(payload, {
      onSuccess: () => {
        toast({ title: "Generation rules saved", tone: "positive" });
        onOpenChange(false);
      },
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Generation rules"
        description="Limits applied to every tailored resume."
      >
        {rules.isPending ? (
          <div className="flex flex-col gap-lp-3">
            <Skeleton shape="block" className="h-lp-control" />
            <Skeleton shape="block" className="h-lp-control" />
            <Skeleton shape="block" className="h-lp-control" />
          </div>
        ) : rules.isError ? (
          <ErrorState
            title="The generation rules could not be loaded"
            cause={rules.error.message}
            action={
              <Button variant="secondary" size="sm" onClick={() => void rules.refetch()}>
                Try again
              </Button>
            }
          />
        ) : rules.data.length === 0 ? (
          <p className="text-lp-body text-lp-ink-secondary">
            There are no generation rules configured. Defaults apply to every run.
          </p>
        ) : (
          <form data-testid="rules-form" onSubmit={submit}>
            <div className="grid max-h-[50dvh] gap-lp-4 overflow-y-auto pr-lp-1 sm:grid-cols-2">
              {rules.data.map((rule) => {
                const id = ruleId(rule);
                return (
                  <Input
                    key={id}
                    id={`rule-${rule.section}-${rule.rule_key}`}
                    label={`${humanize(rule.section)}, ${humanize(rule.rule_key)}`}
                    type="number"
                    inputMode="numeric"
                    value={draft[id] ?? rule.rule_value}
                    onChange={(event) =>
                      setDraft((current) => ({ ...current, [id]: event.target.value }))
                    }
                    className="font-lp-mono tabular-nums"
                  />
                );
              })}
            </div>

            {update.isError ? (
              <p role="alert" className="mt-lp-4 text-lp-caption text-lp-critical">
                {update.error.message}
              </p>
            ) : null}

            <DialogFooter>
              <Button
                variant="ghost"
                onClick={() =>
                  reset.mutate(undefined, {
                    onSuccess: () => toast({ title: "Generation rules reset" }),
                  })
                }
                loading={reset.isPending}
                loadingLabel="Resetting"
              >
                Reset to defaults
              </Button>
              <Button
                type="submit"
                variant="primary"
                loading={update.isPending}
                loadingLabel="Saving"
                data-testid="rules-save"
              >
                Save rules
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
