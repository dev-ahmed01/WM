'use client';

import React, { useEffect, useState } from 'react';
import { useRequireRole } from '@/lib/auth';
import { apiClient, PaginatedKnowledgeItems, KnowledgeItemDetail } from '@/lib/api-client';
import Link from 'next/link';

export default function KnowledgeStudioPage() {
  const { loading: authLoading } = useRequireRole(['admin']);
  const [data, setData] = useState<PaginatedKnowledgeItems | null>(null);
  const [loadingData, setLoadingData] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchKnowledgeItems() {
      try {
        setLoadingData(true);
        setError(null);
        const res = await apiClient<PaginatedKnowledgeItems>('/knowledge');
        setData(res);
      } catch (err: any) {
        console.error('Failed to load knowledge items:', err);
        setError(err?.message || 'Failed to load knowledge documents.');
      } finally {
        setLoadingData(false);
      }
    }

    if (!authLoading) {
      fetchKnowledgeItems();
    }
  }, [authLoading]);

  if (authLoading || loadingData) {
    return <div className="p-8">Loading Knowledge Studio...</div>;
  }

  if (error) {
    return (
      <div className="p-8 max-w-6xl mx-auto">
        <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-md">
          <p className="font-semibold">Error Loading Documents</p>
          <p className="text-sm">{error}</p>
        </div>
      </div>
    );
  }

  const items = data?.items || [];

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Knowledge Studio</h1>
        <Link
          href="/knowledge-studio/upload"
          className="bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-blue-700"
        >
          Upload New Document
        </Link>
      </div>

      {items.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-lg p-12 text-center text-gray-500">
          <p className="text-lg font-medium mb-2">No documents found</p>
          <p className="text-sm mb-4">Get started by uploading your first SOP, policy, or manual.</p>
          <Link
            href="/knowledge-studio/upload"
            className="inline-block bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-blue-700"
          >
            Upload Document
          </Link>
        </div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200 text-xs text-gray-500 font-semibold uppercase">
                <th className="p-4">Title</th>
                <th className="p-4">Department</th>
                <th className="p-4">Status</th>
                <th className="p-4">Version</th>
                <th className="p-4">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 text-sm text-gray-700">
              {items.map((detail: KnowledgeItemDetail) => {
                const activeVer = detail.published_version || detail.latest_version;
                const statusStr = activeVer?.status?.toUpperCase() || 'UNKNOWN';
                const versionNum = activeVer?.version_number ? `v1.${activeVer.version_number - 1}` : 'v1.0';

                return (
                  <tr key={detail.item.id}>
                    <td className="p-4 font-medium">{detail.item.title}</td>
                    <td className="p-4">{detail.item.department_id}</td>
                    <td className="p-4">
                      <span
                        className={`text-xs px-2 py-1 rounded-full font-semibold ${
                          statusStr === 'PUBLISHED'
                            ? 'bg-green-100 text-green-800'
                            : statusStr === 'STAGED' || statusStr === 'PROCESSED'
                            ? 'bg-yellow-100 text-yellow-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}
                      >
                        {statusStr}
                      </span>
                    </td>
                    <td className="p-4">{versionNum}</td>
                    <td className="p-4">
                      <Link href={`/knowledge-studio/${detail.item.id}`} className="text-blue-600 hover:underline">
                        View / Edit
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
