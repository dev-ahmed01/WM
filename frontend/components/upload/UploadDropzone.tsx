import React, { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api-client';

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

      if (res.compilation_status === 'VALIDATION_FAILED' || res.deployment_status === 'FAILED') {
        setProgress(100);
        const err = res.validation_errors?.[0] || res.message || 'Compilation validation failed.';
        setErrorDetails(err);
        setMessage(`Upload compilation failed for "${file.name}"`);
        return;
      }

      setProgress(100);
      setMessage(`Successfully uploaded and compiled "${file.name}" (${res.number_of_states || 1} state, ${res.number_of_steps || 1} steps)!`);
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
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-8 text-center transition space-y-4 ${
          isDragging
            ? 'border-blue-500 bg-blue-50/80 shadow-md ring-2 ring-blue-400/50'
            : 'border-gray-300 bg-gray-50 hover:bg-gray-100'
        }`}
      >
        <div className="flex flex-col md:flex-row gap-4 text-left max-w-lg mx-auto">
          <div className="flex-1">
            <label className="block text-xs font-semibold text-gray-700 mb-1">Document Title</label>
            <input
              type="text"
              placeholder="e.g. Safety Valve Maintenance SOP"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={uploading || departments.length === 0}
              className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div className="w-full md:w-44">
            <label className="block text-xs font-semibold text-gray-700 mb-1">Department</label>
            <select
              value={departmentId}
              onChange={(e) => setDepartmentId(e.target.value)}
              disabled={uploading}
              className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              {departments.map((department) => (
                <option key={department.id} value={department.id}>{department.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <input
            type="file"
            id="file-upload"
            className="hidden"
            onChange={handleFileUpload}
            disabled={uploading}
            accept=".md,text/markdown"
          />
          <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center">
            <svg
              className={`w-12 h-12 mb-3 transition-colors ${
                isDragging ? 'text-blue-600 scale-110' : 'text-gray-400'
              }`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
            <span className="text-sm font-medium text-gray-700">
              {isDragging ? 'Drop file here to upload' : 'Click to upload or drag & drop document'}
            </span>
            <span className="text-xs text-gray-500 mt-1">OWD Markdown (.md), UTF-8, up to 25 MB</span>
          </label>
        </div>

        {uploading && (
          <div className="mt-4 w-full bg-gray-200 rounded-full h-2.5">
            <div
              className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}

        {message && !errorDetails && !uploadedDocId && (
          <p className="mt-3 text-xs text-gray-600 font-medium">{message}</p>
        )}
      </div>

      {errorDetails && (
        <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-md text-sm">
          <p className="font-semibold mb-1">Upload Compilation Error</p>
          <p>{errorDetails}</p>
        </div>
      )}

      {uploadedDocId && (
        <div className="bg-green-50 border border-green-200 text-green-800 p-4 rounded-md text-sm space-y-3">
          <p className="font-semibold">{message}</p>
          <div className="flex gap-3">
            <a
              href={`/knowledge-studio/${uploadedDocId}`}
              className="inline-block bg-blue-600 text-white px-3 py-1.5 rounded text-xs font-semibold hover:bg-blue-700"
            >
              View Document Details
            </a>
            <a
              href="/knowledge-studio"
              className="inline-block bg-gray-100 text-gray-800 border border-gray-300 px-3 py-1.5 rounded text-xs font-semibold hover:bg-gray-200"
            >
              Back to Knowledge Studio
            </a>
          </div>
        </div>
      )}
    </div>
  );
};
