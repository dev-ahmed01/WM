'use client';

import React, { useEffect, useState } from 'react';
import { useRequireRole } from '@/lib/auth';
import { apiClient, KnowledgeItemDetail, KnowledgeVersionHistory, KnowledgeVersion } from '@/lib/api-client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Save, Trash2, ArrowLeft, CheckCircle2, AlertCircle } from 'lucide-react';

export default function DocumentDetailsPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const { loading: authLoading } = useRequireRole(['admin']);
  const [detail, setDetail] = useState<KnowledgeItemDetail | null>(null);
  const [versionHistory, setVersionHistory] = useState<KnowledgeVersionHistory | null>(null);
  const [loadingData, setLoadingData] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Edit form state
  const [title, setTitle] = useState('');
  const [departmentId, setDepartmentId] = useState('dept_eng');
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  useEffect(() => {
    async function fetchDocumentData() {
      try {
        setLoadingData(true);
        setError(null);
        const [itemDetail, history] = await Promise.all([
          apiClient<KnowledgeItemDetail>(`/knowledge/${params.id}`),
          apiClient<KnowledgeVersionHistory>(`/knowledge/${params.id}/versions`),
        ]);
        setDetail(itemDetail);
        setVersionHistory(history);
        setTitle(itemDetail.item.title);
        setDepartmentId(itemDetail.item.department_id || 'dept_eng');
      } catch (err: any) {
        console.error('Failed to load document details:', err);
        setError(err?.message || 'Failed to load document details.');
      } finally {
        setLoadingData(false);
      }
    }

    if (!authLoading && params.id) {
      fetchDocumentData();
    }
  }, [authLoading, params.id]);

  const handleUpdateMetadata = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || isSaving) return;

    setIsSaving(true);
    setFeedback(null);

    try {
      const updatedItem = await apiClient<any>(`/knowledge/${params.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          title: title.trim(),
          department_id: departmentId,
        }),
      });

      setDetail((prev) =>
        prev
          ? {
              ...prev,
              item: { ...prev.item, title: updatedItem.title, department_id: updatedItem.department_id },
            }
          : null
      );

      setFeedback({ type: 'success', message: 'Document metadata updated successfully.' });
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Failed to update metadata.' });
    } finally {
      setIsSaving(false);
    }
  };

  const handleArchiveDocument = async () => {
    if (!confirm('Are you sure you want to archive this document? This will soft-delete all versions.')) {
      return;
    }

    setIsDeleting(true);
    setFeedback(null);

    try {
      await apiClient(`/knowledge/${params.id}`, {
        method: 'DELETE',
      });

      setFeedback({ type: 'success', message: 'Document archived successfully. Redirecting...' });
      setTimeout(() => {
        router.push('/knowledge-studio');
      }, 1200);
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Failed to archive document.' });
      setIsDeleting(false);
    }
  };

  if (authLoading || loadingData) {
    return <div className="p-8">Loading Document Details & Edit Form...</div>;
  }

  if (error || !detail) {
    return (
      <div className="p-8 max-w-4xl mx-auto space-y-4">
        <Link href="/knowledge-studio" className="text-blue-600 hover:underline text-sm inline-flex items-center gap-1">
          <ArrowLeft className="h-4 w-4" /> Back to Knowledge Studio
        </Link>
        <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-md">
          <p className="font-semibold">Document Not Found</p>
          <p className="text-sm">{error || `Could not find document with ID '${params.id}'.`}</p>
        </div>
      </div>
    );
  }

  const { item, latest_version, published_version } = detail;
  const activeVer = published_version || latest_version;

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <Link href="/knowledge-studio" className="text-blue-600 hover:underline text-sm inline-flex items-center gap-1">
          <ArrowLeft className="h-4 w-4" /> Back to Knowledge Studio
        </Link>
        <Button
          variant="destructive"
          size="sm"
          onClick={handleArchiveDocument}
          disabled={isDeleting}
          className="flex items-center gap-2"
        >
          <Trash2 className="h-4 w-4" />
          {isDeleting ? 'Archiving...' : 'Archive Document'}
        </Button>
      </div>

      {feedback && (
        <div
          className={`p-4 rounded-md flex items-center gap-2 text-sm ${
            feedback.type === 'success'
              ? 'bg-green-50 text-green-800 border border-green-200'
              : 'bg-red-50 text-red-800 border border-red-200'
          }`}
        >
          {feedback.type === 'success' ? (
            <CheckCircle2 className="h-5 w-5 text-green-600 flex-shrink-0" />
          ) : (
            <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0" />
          )}
          <span>{feedback.message}</span>
        </div>
      )}

      <div className="border-b pb-4">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold text-gray-900">{item.title}</h1>
          {item.workflow_code && (
            <span className="bg-blue-100 text-blue-800 text-xs font-mono px-2 py-0.5 rounded font-semibold">
              {item.workflow_code}
            </span>
          )}
        </div>
        <p className="text-sm text-gray-500 mt-1">
          Workflow ID: {item.id} • Status:{' '}
          <span className="font-semibold text-gray-700">{activeVer?.status?.toUpperCase() || 'STAGED'}</span>
          {item.category && ` • Category: ${item.category}`}
        </p>
      </div>

      {/* State Machine Graph Breakdown */}
      {detail.states && detail.states.length > 0 && (
        <div className="bg-white p-6 border border-gray-200 rounded-lg shadow-sm">
          <h2 className="text-lg font-semibold mb-3 text-gray-800 flex items-center justify-between">
            <span>Compiled OWD State Graph</span>
            <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded">
              {detail.states.length} States
            </span>
          </h2>
          <div className="space-y-3 divide-y divide-gray-100">
            {detail.states.map((st) => (
              <div key={st.id} className="pt-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono bg-blue-50 text-blue-700 px-2 py-0.5 rounded border border-blue-200">
                      {st.state_key}
                    </span>
                    <span className="text-sm font-semibold text-gray-800">{st.title}</span>
                  </div>
                  <span className="text-xs text-gray-400 capitalize">{st.state_type}</span>
                </div>
                {st.description && <p className="text-xs text-gray-600 mt-1">{st.description}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Edit Form */}
      <div className="bg-white p-6 border border-gray-200 rounded-lg shadow-sm">
        <h2 className="text-lg font-semibold mb-4 text-gray-800">Edit Metadata</h2>
        <form onSubmit={handleUpdateMetadata} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Workflow Title</label>
            <input
              type="text"
              required
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={isSaving}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Department Scope</label>
            <select
              value={departmentId}
              onChange={(e) => setDepartmentId(e.target.value)}
              disabled={isSaving}
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="dept_eng">Engineering (dept_eng)</option>
              <option value="dept_ops">Operations (dept_ops)</option>
              <option value="dept_hr">Human Resources (dept_hr)</option>
              <option value="dept_safety">Safety & Compliance (dept_safety)</option>
            </select>
          </div>
          <Button type="submit" disabled={isSaving} className="flex items-center gap-2">
            <Save className="h-4 w-4" />
            {isSaving ? 'Saving Changes...' : 'Save Metadata'}
          </Button>
        </form>
      </div>

      {/* Version History */}
      <div className="bg-white p-6 border border-gray-200 rounded-lg shadow-sm">
        <h2 className="text-lg font-semibold mb-3">Version History</h2>
        {!versionHistory || versionHistory.versions.length === 0 ? (
          <p className="text-sm text-gray-500">No version history records found.</p>
        ) : (
          <ul className="space-y-3 text-sm text-gray-700">
            {versionHistory.versions.map((ver: KnowledgeVersion) => {
              const isPublished = published_version?.id === ver.id;
              const isLatest = latest_version?.id === ver.id;
              return (
                <li key={ver.id} className="flex justify-between border-b pb-2">
                  <div>
                    <span className="font-medium">Version {ver.version_number} ({ver.semantic_version || '1.0.0'})</span>
                    <span className="text-xs ml-2 text-gray-500">
                      ({ver.status}) {isPublished ? '• Active Published' : isLatest ? '• Latest Draft' : ''}
                    </span>
                  </div>
                  <span className="text-gray-400">{ver.created_at || 'N/A'}</span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
