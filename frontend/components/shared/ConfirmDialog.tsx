import React, { useEffect } from 'react';
import { AlertTriangle, CheckCircle2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  busy?: boolean;
  confirmDisabled?: boolean;
  tone?: 'default' | 'danger';
  value?: string;
  valueLabel?: string;
  valuePlaceholder?: string;
  onValueChange?: (value: string) => void;
  onConfirm: () => void;
  onClose: () => void;
}

export function ConfirmDialog({ open, title, description, confirmLabel, busy, confirmDisabled = false, tone = 'danger', value, valueLabel, valuePlaceholder, onValueChange, onConfirm, onClose }: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return undefined;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onClose();
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [busy, onClose, open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] grid place-items-center p-4" role="presentation">
      <button type="button" className="absolute inset-0 bg-slate-950/55 backdrop-blur-sm" onClick={onClose} aria-label="Close dialog" />
      <section role="alertdialog" aria-modal="true" aria-labelledby="confirm-dialog-title" className="relative w-full max-w-md rounded-2xl border bg-white p-5 shadow-lift sm:p-6">
        <button type="button" onClick={onClose} aria-label="Close dialog" className="absolute right-4 top-4 grid h-8 w-8 place-items-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"><X className="h-4 w-4" /></button>
        <div className={`grid h-10 w-10 place-items-center rounded-xl ${tone === 'danger' ? 'bg-red-50 text-red-600' : 'bg-emerald-50 text-emerald-700'}`}>{tone === 'danger' ? <AlertTriangle className="h-5 w-5" /> : <CheckCircle2 className="h-5 w-5" />}</div>
        <h2 id="confirm-dialog-title" className="mt-4 text-lg font-semibold tracking-tight text-foreground">{title}</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
        {onValueChange ? (
          <label className="mt-5 block">
            <span className="wm-label">{valueLabel}</span>
            <textarea className="wm-input min-h-24 resize-none" value={value} onChange={(event) => onValueChange(event.target.value)} placeholder={valuePlaceholder} autoFocus />
          </label>
        ) : null}
        <div className="mt-6 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose} disabled={busy} autoFocus={!onValueChange}>Cancel</Button>
          <Button type="button" variant={tone === 'danger' ? 'destructive' : 'default'} onClick={onConfirm} disabled={busy || confirmDisabled || (onValueChange ? !value?.trim() : false)}>{busy ? 'Working…' : confirmLabel}</Button>
        </div>
      </section>
    </div>
  );
}
