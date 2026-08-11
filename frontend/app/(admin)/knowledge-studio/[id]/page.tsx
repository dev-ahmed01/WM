'use client';

import React, { use, useEffect, useState } from 'react';
import { useRequireRole } from '@/lib/auth';
import { apiClient, KnowledgeItemDetail, KnowledgeVersionHistory, KnowledgeVersion } from '@/lib/api-client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Save, Trash2, ArrowLeft, CheckCircle2, AlertCircle } from 'lucide-react';
import { LoadingState } from '@/components/shared/LoadingState';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';

export default function DocumentDetailsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { loading: authLoading } = useRequireRole(['admin']);
  const [detail, setDetail] = useState<KnowledgeItemDetail | null>(null);
  const [versionHistory, setVersionHistory] = useState<KnowledgeVersionHistory | null>(null);
  const [loadingData, setLoadingData] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Edit form state
  const [title, setTitle] = useState('');
  const [departmentId, setDepartmentId] = useState('');
  const [departments, setDepartments] = useState<Array<{ id: string; name: string }>>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  useEffect(() => {
    async function fetchDocumentData() {
      try {
        setLoadingData(true);
        setError(null);
        const [itemDetail, history, activeDepartments] = await Promise.all([
          apiClient<KnowledgeItemDetail>(`/knowledge/${id}`),
          apiClient<KnowledgeVersionHistory>(`/knowledge/${id}/versions`),
          apiClient<Array<{ id: string; name: string }>>('/knowledge/departments'),
        ]);
        setDetail(itemDetail);
        setVersionHistory(history);
        setTitle(itemDetail.item.title);
        setDepartments(activeDepartments);
        setDepartmentId(itemDetail.item.department_id);
      } catch (err: any) {
        console.error('Failed to load document details:', err);
        setError(err?.message || 'Failed to load document details.');
      } finally {
        setLoadingData(false);
      }
    }

    if (!authLoading && id) {
      fetchDocumentData();
    }
  }, [authLoading, id]);

  const handleUpdateMetadata = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || isSaving) return;

    setIsSaving(true);
    setFeedback(null);

    try {
      const updatedItem = await apiClient<any>(`/knowledge/${id}`, {
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
    setIsDeleting(true);
    setFeedback(null);

    try {
      await apiClient(`/knowledge/${id}`, {
        method: 'DELETE',
      });

      setFeedback({ type: 'success', message: 'Document archived successfully. Redirecting...' });
      setArchiveOpen(false);
      setTimeout(() => {
        router.push('/knowledge-studio');
      }, 1200);
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Failed to archive document.' });
      setIsDeleting(false);
    }
  };

  if (authLoading || loadingData) {
    return <LoadingState label="Loading workflow details" />;
  }

  if (error || !detail) {
    return (
      <div className="wm-page max-w-5xl space-y-4">
        <Link href="/knowledge-studio" className="inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline">
          <ArrowLeft className="h-4 w-4" /> Back to Knowledge Studio
        </Link>
        <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-red-700">
          <p className="font-semibold">Document Not Found</p>
          <p className="text-sm">{error || `Could not find document with ID '${id}'.`}</p>
        </div>
      </div>
    );
  }

  const { item, latest_version, published_version } = detail;
  const activeVer = published_version || latest_version;

  return (
    <div className="wm-page max-w-5xl space-y-6">
      <div className="flex items-center justify-between">
        <Link href="/knowledge-studio" className="inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline">
          <ArrowLeft className="h-4 w-4" /> Back to Knowledge Studio
        </Link>
        <Button
          variant="destructive"
          size="sm"
          onClick={() => setArchiveOpen(true)}
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

      <div className="border-b pb-6 pt-2">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-[-0.03em] text-foreground sm:text-3xl">{item.title}</h1>
          {item.workflow_code && (
            <span className="rounded-lg bg-emerald-50 px-2 py-1 font-mono text-xs font-semibold text-emerald-800">
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
        <div className="wm-panel p-5 sm:p-6">
          <h2 className="mb-4 flex items-center justify-between text-base font-semibold text-foreground">
            <span>Compiled OWD State Graph</span>
            <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
              {detail.states.length} States
            </span>
          </h2>
          <div className="space-y-3 divide-y divide-border/70">
            {detail.states.map((st) => (
              <div key={st.id} className="pt-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1 font-mono text-[10px] text-emerald-800">
                      {st.state_key}
                    </span>
                    <span className="text-sm font-semibold text-foreground">{st.title}</span>
                  </div>
                  <span className="text-xs capitalize text-muted-foreground">{st.state_type}</span>
                </div>
                {st.description && <p className="mt-1 text-xs leading-5 text-muted-foreground">{st.description}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Edit Form */}
      <div className="wm-panel p-5 sm:p-6">
        <h2 className="mb-5 text-base font-semibold text-foreground">Workflow metadata</h2>
        <form onSubmit={handleUpdateMetadata} className="space-y-4">
          <div>
            <label className="wm-label">Workflow title</label>
            <input
              type="text"
              required
              className="wm-input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={isSaving}
            />
          </div>
          <div>
            <label className="wm-label">Department scope</label>
            <select
              value={departmentId}
              onChange={(e) => setDepartmentId(e.target.value)}
              disabled={isSaving}
              className="wm-input"
            >
              {departments.map((department) => (
                <option key={department.id} value={department.id}>
                  {department.name} ({department.id})
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" disabled={isSaving} className="flex items-center gap-2">
            <Save className="h-4 w-4" />
            {isSaving ? 'Saving Changes...' : 'Save Metadata'}
          </Button>
        </form>
      </div>

      {/* Version History */}
      <div className="wm-panel p-5 sm:p-6">
        <h2 className="mb-4 text-base font-semibold">Version history</h2>
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
      <ConfirmDialog
        open={archiveOpen}
        title="Archive this workflow?"
        description="All versions will be soft-deleted and removed from employee guidance. This does not permanently erase audit history."
        confirmLabel="Archive workflow"
        busy={isDeleting}
        onConfirm={handleArchiveDocument}
        onClose={() => !isDeleting && setArchiveOpen(false)}
      />
    </div>
  );
}
