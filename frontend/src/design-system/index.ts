/**
 * Letterpress design system (docs/design/DESIGN-SYSTEM.md).
 *
 * Tokens live in `tokens.css`, imported once from `src/app/globals.css`. No
 * component in this directory contains a colour literal; every value comes
 * through a `--lp-*` custom property by way of a Tailwind `lp-*` utility.
 *
 * Built in task 1.4 alongside the existing UI. Task 2.3 migrates
 * `src/components/**` onto it and removes the legacy layer.
 */
export { cn, focusRing, pressable } from "./cn";

export { Button } from "./Button";
export type { ButtonProps, ButtonSize, ButtonVariant } from "./Button";

export { IconButton } from "./IconButton";
export type { IconButtonProps, IconButtonSize, IconButtonVariant } from "./IconButton";

export { Input } from "./Input";
export type { InputProps } from "./Input";

export { Textarea } from "./Textarea";
export type { TextareaProps } from "./Textarea";

export { Tabs, TabsContent, TabsList, TabsTrigger } from "./Tabs";

export { Dialog, DialogClose, DialogContent, DialogFooter, DialogTrigger } from "./Dialog";
export type { DialogContentProps } from "./Dialog";

export { AlertDialog, AlertDialogContent, AlertDialogTrigger } from "./AlertDialog";
export type { AlertDialogContentProps } from "./AlertDialog";

export { Tooltip, TooltipProvider } from "./Tooltip";
export type { TooltipProps } from "./Tooltip";

export { ToastHost, useToast } from "./Toast";
export type { ToastMessage, ToastTone } from "./Toast";

export { Chip } from "./Chip";
export type { ChipProps, ChipTone } from "./Chip";

export { Skeleton } from "./Skeleton";
export type { SkeletonProps } from "./Skeleton";

export { ProgressRail } from "./ProgressRail";
export type { ProgressRailProps, ProgressStage } from "./ProgressRail";

export { ScoreDial } from "./ScoreDial";
export type { ScoreDialProps } from "./ScoreDial";

export { ModeSwitch } from "./ModeSwitch";
export type { DocumentMode } from "./ModeSwitch";

export { DocumentFrame } from "./DocumentFrame";
export type { DocumentFrameProps } from "./DocumentFrame";

export { EmptyState } from "./EmptyState";
export type { EmptyStateProps } from "./EmptyState";

export { ErrorState } from "./ErrorState";
export type { ErrorStateProps } from "./ErrorState";
