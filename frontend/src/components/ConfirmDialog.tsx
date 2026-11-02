"use client";

import { useEffect, useRef } from "react";

import { Button } from "@/components/Button";

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Подтвердить",
  cancelLabel = "Отмена",
  variant = "default",
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "default";
  onConfirm: () => void;
  onCancel: () => void;
}) {
  // Map the dialog-level variant to the Button-level one: "default"
  // confirms with the ordinary primary accent, "danger" is the same
  // coral fill but semantically marked.
  const confirmVariant = variant === "danger" ? "danger" : "primary";
  const cancelRef = useRef<HTMLButtonElement | null>(null);
  const confirmRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    // Focus lands on Cancel: the safe choice, Enter confirms nothing
    // by accident.
    cancelRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
        return;
      }
      if (event.key === "Tab") {
        // Focus trap: Tab cycles Cancel -> Confirm -> Cancel.
        const buttons = [cancelRef.current, confirmRef.current].filter(
          (el): el is HTMLButtonElement => el !== null,
        );
        if (buttons.length === 0) return;
        const first = buttons[0];
        const last = buttons[buttons.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onCancel}
      role="presentation"
    >
      <div
        ref={dialogRef}
        className="mx-4 w-full max-w-md rounded-sm border border-line bg-bg p-6"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
      >
        <h2
          id="confirm-dialog-title"
          className="mb-3 font-serif text-2xl font-semibold"
        >
          {title}
        </h2>
        <p className="mb-8 text-sm leading-relaxed text-fg-muted">{message}</p>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel} ref={cancelRef}>
            {cancelLabel}
          </Button>
          <Button variant={confirmVariant} onClick={onConfirm} ref={confirmRef}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
