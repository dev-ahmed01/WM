import React, { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { AlertCircle, ArrowRight, CheckCircle2, FileCode2, UploadCloud } from 'lucide-react';

export const UploadDropzone: React.FC = () => {
  const [title, setTitle] = useState('');
  const [departmentId, setDepartmentId] = useState('');
  const [departments, setDepartments] = useState<Array<{ id: string; name: string }>>([]);
  const [uploading, setUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState<string | null>(null);

  const [uploadedDocId, setUploadedDocId] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<string | null>(null);

  useEffect(() => {
    apiClient<Array<{ id: string; name: string }>>('/knowledge/departments')
      .then((items) => {
        setDepartments(items);
        if (items.length > 0) setDepartmentId(items[0].id);
      })
      .catch((err: Error) => setErrorDetails(err.message || 'Unable to load departments'));
  }, []);

  const processFile = async (file: File) => {
    const docTitle = title.trim() || file.name.replace(/\.[^/.]+$/, '');
    const docDept = departmentId.trim();
    if (!file.name.toLowerCase().endsWith('.md')) {
      setErrorDetails('Only OWD Markdown (.md) files are supported.');
      setMessage('Upload failed');
      return;
    }
    if (!docDept) {
      setErrorDetails('Select an active department before uploading.');
      setMessage('Upload failed');
      return;
    }

    setUploading(true);
    setProgress(30);
    setMessage('Uploading file and compiling operational workflow...');
    setErrorDetails(null);
    setUploadedDocId(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('title', docTitle);
      formData.append('department_id', docDept);

      setProgress(60);
      const res: any = await apiClient('/knowledge/upload', {
        method: 'POST',
        body: formData,
      });

      if (res.compilation_status !== 'SUCCESS' || res.deployment_status !== 'PUBLISHED') {
        setProgress(100);
        const err = res.validation_errors?.[0] || res.message || 'Compilation validation failed.';
        setErrorDetails(err);
        setMessage(`Upload compilation failed for "${file.name}"`);
        return;
      }

      setProgress(100);
      setMessage(`Successfully uploaded and compiled "${file.name}" (${res.number_of_states ?? 0} states, ${res.number_of_steps ?? 0} steps)!`);
      if (res.knowledge_item_id) {
        setUploadedDocId(res.knowledge_item_id);
      }
      setTitle('');
    } catch (err: any) {
      setErrorDetails(err.message || 'An unexpected error occurred');
      setMessage(`Upload failed`);
    } finally {
      setUploading(false);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      await processFile(file);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (!uploading) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    if (uploading) return;

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      await processFile(files[0]);
    }
  };

  return (
    <div className="space-y-4">
      <section className="wm-panel overflow-hidden">
        <div className="grid gap-5 border-b bg-muted/35 p-5 sm:grid-cols-[1fr_15rem] sm:p-6">
          <label><span className="wm-label">Document title</span><input type="text" placeholder="e.g. Inbound Shipment Receiving" value={title} onChange={(event) => setTitle(event.target.value)} disabled={uploading || departments.length === 0} className="wm-input" /></label>
          <label><span className="wm-label">Department scope</span><select value={departmentId} onChange={(event) => setDepartmentId(event.target.value)} disabled={uploading} className="wm-input">{departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}</select></label>
        </div>

        <div onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop} className={`m-5 rounded-2xl border-2 border-dashed p-8 text-center transition sm:m-6 sm:p-12 ${isDragging ? 'border-emerald-500 bg-emerald-50 ring-4 ring-emerald-100' : 'border-border bg-[#fafcfb] hover:border-emerald-300 hover:bg-emerald-50/35'}`}>
          <input type="file" id="file-upload" className="sr-only" onChange={handleFileUpload} disabled={uploading} accept=".md,text/markdown" />
          <label htmlFor="file-upload" className="mx-auto flex max-w-md cursor-pointer flex-col items-center">
            <span className={`grid h-14 w-14 place-items-center rounded-2xl transition ${isDragging ? 'scale-105 bg-emerald-600 text-white' : 'bg-emerald-50 text-emerald-700'}`}><UploadCloud className="h-6 w-6" /></span>
            <span className="mt-4 text-sm font-semibold text-foreground">{isDragging ? 'Release to upload this workflow' : 'Drop your OWD Markdown file here'}</span>
            <span className="mt-1 text-xs leading-5 text-muted-foreground">or click to choose a file · UTF-8 `.md` · maximum 25 MB</span>
          </label>

          {uploading ? <div className="mx-auto mt-6 max-w-md"><div className="flex items-center justify-between text-[10px] font-semibold text-muted-foreground"><span>Validating and compiling</span><span>{progress}%</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-200"><div className="h-full rounded-full bg-emerald-600 transition-all duration-300" style={{ width: `${progress}%` }} /></div></div> : null}
          {message && !errorDetails && !uploadedDocId ? <p className="mt-4 text-xs font-medium text-muted-foreground" aria-live="polite">{message}</p> : null}
        </div>

        <div className="grid gap-3 border-t bg-muted/25 px-5 py-4 text-xs text-muted-foreground sm:grid-cols-3 sm:px-6">
          <span className="flex items-center gap-2"><FileCode2 className="h-4 w-4 text-emerald-700" />Parse OWD structure</span>
          <span className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-700" />Validate all transitions</span>
          <span className="flex items-center gap-2"><ArrowRight className="h-4 w-4 text-emerald-700" />Publish atomically</span>
        </div>
      </section>

      {errorDetails ? <div role="alert" className="flex gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"><AlertCircle className="mt-0.5 h-5 w-5 flex-none" /><div><p className="font-semibold">Compilation failed</p><p className="mt-1 leading-5">{errorDetails}</p></div></div> : null}

      {uploadedDocId ? <div className="flex flex-col gap-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-5 text-sm text-emerald-900 sm:flex-row sm:items-center sm:justify-between"><div className="flex gap-3"><CheckCircle2 className="mt-0.5 h-5 w-5 flex-none text-emerald-700" /><div><p className="font-semibold">Workflow published</p><p className="mt-1 text-xs leading-5 text-emerald-800">{message}</p></div></div><div className="flex flex-none gap-2"><a href="/knowledge-studio" className="rounded-xl border border-emerald-200 bg-white px-3 py-2 text-xs font-semibold">Library</a><a href={`/knowledge-studio/${uploadedDocId}`} className="rounded-xl bg-emerald-700 px-3 py-2 text-xs font-semibold text-white">View workflow</a></div></div> : null}
    </div>
  );
};
