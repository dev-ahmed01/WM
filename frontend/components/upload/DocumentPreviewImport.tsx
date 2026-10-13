'use client';

import React, { useState } from 'react';
import { AlertCircle, FileSearch, FileText, ShieldCheck, UploadCloud } from 'lucide-react';
import { apiClient } from '@/lib/api-client';

type DocumentPreview = {
  filename: string;
  file_type: string;
  text_preview: string;
  total_characters: number;
  preview_truncated: boolean;
  warnings: string[];
  publication_status: 'not_published';
};

const ACCEPTED_FORMATS = '.md,.txt,.csv,.tsv,.json,.html,.htm,.pdf,.docx,.xlsx,.pptx,.rtf';

export function DocumentPreviewImport() {
  const [preview, setPreview] = useState<DocumentPreview | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [isWorking, setIsWorking] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const previewFile = async (file: File) => {
    setError(null);
    setPreview(null);
    setFileName(file.name);
    if (file.size > 25 * 1024 * 1024) {
      setError('This file exceeds the 25 MB preview limit.');
      return;
    }
    const form = new FormData();
    form.append('file', file);
    setIsWorking(true);
    try {
      const response = await apiClient<DocumentPreview>('/knowledge/preview', {
        method: 'POST',
        body: form,
      });
      setPreview(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not extract this document.');
    } finally {
      setIsWorking(false);
    }
  };

  return (
    <div className="space-y-4">
      <section className="wm-panel overflow-hidden">
        <div className="flex items-start gap-3 border-b border-border bg-emerald-50/50 px-5 py-5 sm:px-7">
          <FileSearch className="mt-0.5 h-5 w-5 flex-none text-emerald-700" aria-hidden="true" />
          <div>
            <h2 className="text-base font-semibold text-foreground">Read a document</h2>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              Extract and inspect content before deciding how to structure your knowledge.
              This preview does not publish an SOP or make a document available to employees.
            </p>
          </div>
        </div>

        <div
          className={`m-5 rounded-2xl border-2 border-dashed p-8 text-center transition sm:m-7 sm:p-12 ${dragging ? 'border-emerald-500 bg-emerald-50' : 'border-border bg-[#fbfcfb] hover:border-emerald-300'}`}
          onDragOver={(event) => { event.preventDefault(); if (!isWorking) setDragging(true); }}
          onDragLeave={(event) => { event.preventDefault(); setDragging(false); }}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            if (!isWorking && event.dataTransfer.files[0]) void previewFile(event.dataTransfer.files[0]);
          }}
        >
          <input
            id="document-preview-upload"
            type="file"
            className="sr-only"
            accept={ACCEPTED_FORMATS}
            disabled={isWorking}
            onChange={(event) => {
              const selected = event.currentTarget.files?.[0];
              if (selected) void previewFile(selected);
              event.currentTarget.value = '';
            }}
          />
          <label htmlFor="document-preview-upload" className="mx-auto flex max-w-lg cursor-pointer flex-col items-center">
            <span className="grid h-14 w-14 place-items-center rounded-2xl bg-emerald-50 text-emerald-700">
              <UploadCloud className="h-6 w-6" aria-hidden="true" />
            </span>
            <span className="mt-4 text-sm font-semibold">{isWorking ? 'Reading your document…' : dragging ? 'Release to inspect document' : 'Choose or drop a document'}</span>
            <span className="mt-2 text-xs leading-5 text-muted-foreground">PDF, DOCX, XLSX, PPTX, TXT, MD, CSV, TSV, JSON, HTML, RTF · up to 25 MB</span>
          </label>
        </div>
        <div className="flex items-start gap-2 border-t border-border bg-muted/20 px-5 py-3 text-xs leading-5 text-muted-foreground sm:px-7">
          <ShieldCheck className="mt-0.5 h-4 w-4 flex-none text-emerald-700" aria-hidden="true" />
          Content stays in this review step. Scanned images and image-only PDFs require OCR before they can be reliably imported.
        </div>
      </section>

      {error ? (
        <div role="alert" className="flex gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <AlertCircle className="h-5 w-5 flex-none" aria-hidden="true" />
          <div><p className="font-semibold">Could not read document</p><p className="mt-1">{error}</p></div>
        </div>
      ) : null}

      {preview ? (
        <section className="wm-panel overflow-hidden" aria-label="Extracted document preview">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-5 sm:px-7">
            <div className="flex min-w-0 items-center gap-3">
              <FileText className="h-5 w-5 shrink-0 text-emerald-700" aria-hidden="true" />
              <div className="min-w-0">
                <h3 className="truncate text-sm font-semibold">{preview.filename}</h3>
                <p className="mt-0.5 text-xs text-muted-foreground">{preview.file_type.toUpperCase()} · {preview.total_characters.toLocaleString()} extracted characters · Not published</p>
              </div>
            </div>
          </div>
          {preview.warnings.length ? (
            <div className="space-y-1 border-b border-amber-200 bg-amber-50 px-5 py-3 text-xs leading-5 text-amber-900 sm:px-7">
              {preview.warnings.map((warning) => <p key={warning}>{warning}</p>)}
            </div>
          ) : null}
          <pre className="max-h-[26rem] overflow-auto whitespace-pre-wrap break-words p-5 font-sans text-sm leading-6 text-foreground sm:p-7">{preview.text_preview}</pre>
          {preview.preview_truncated ? <p className="border-t border-border px-5 py-3 text-xs text-muted-foreground sm:px-7">Preview limited to the first 12,000 characters. The entire document has not been shown.</p> : null}
        </section>
      ) : fileName && isWorking ? (
        <p aria-live="polite" className="text-sm text-muted-foreground">Extracting readable text from {fileName}…</p>
      ) : null}
    </div>
  );
}
