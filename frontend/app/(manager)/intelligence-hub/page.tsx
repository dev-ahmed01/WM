'use client';

import React, { useEffect, useState } from 'react';
import { useRequireRole } from '@/lib/auth';
import { MetricCard } from '@/components/dashboard/MetricCard';
import { apiClient } from '@/lib/api-client';

export default function IntelligenceHubPage() {
  const { loading } = useRequireRole(['manager', 'admin']);

  const [sopUsage, setSopUsage] = useState<any[]>([]);
  const [confusingProcedures, setConfusingProcedures] = useState<any[]>([]);
  const [departmentAdoption, setDepartmentAdoption] = useState<any[]>([]);
  const [confidenceTrends, setConfidenceTrends] = useState<any[]>([]);
  const [faqs, setFaqs] = useState<any[]>([]);
  const [escalations, setEscalations] = useState<any[]>([]);
  const [dataLoading, setDataLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchAnalyticsData() {
      try {
        setDataLoading(true);
        setFetchError(null);

        const [usageData, confusingData, adoptionData, trendsData, faqData, escalationData] = await Promise.all([
          apiClient<any[]>('/analytics/sop-usage'),
          apiClient<any[]>('/analytics/confusing-procedures'),
          apiClient<any[]>('/analytics/department-adoption'),
          apiClient<any[]>('/analytics/confidence-trends'),
          apiClient<any[]>('/analytics/faqs'),
          apiClient<any[]>('/analytics/escalations'),
        ]);

        setSopUsage(Array.isArray(usageData) ? usageData : []);
        setConfusingProcedures(Array.isArray(confusingData) ? confusingData : []);
        setDepartmentAdoption(Array.isArray(adoptionData) ? adoptionData : []);
        setConfidenceTrends(Array.isArray(trendsData) ? trendsData : []);
        setFaqs(Array.isArray(faqData) ? faqData : []);
        setEscalations(Array.isArray(escalationData) ? escalationData : []);
      } catch (err: any) {
        console.error('Failed to load analytics data:', err);
        setFetchError(err?.message || 'Failed to connect to analytics service.');
      } finally {
        setDataLoading(false);
      }
    }

    if (!loading) {
      fetchAnalyticsData();
    }
  }, [loading]);

  if (loading || dataLoading) {
    return <div className="p-8 text-gray-600 font-medium">Loading Intelligence Hub...</div>;
  }

  const totalExecutions = sopUsage.reduce((acc, curr) => acc + (curr.total_executions || 0), 0);
  const avgConfidence = confidenceTrends.length
    ? `${(confidenceTrends.reduce((acc, curr) => acc + (curr.avg_confidence_score || 0), 0) / confidenceTrends.length * 100).toFixed(1)}%`
    : 'No data yet';

  const avgAdoptionRate = departmentAdoption.length
    ? `${(departmentAdoption.reduce((acc, curr) => acc + (curr.adoption_rate_pct || 0), 0) / departmentAdoption.length).toFixed(0)}%`
    : 'No data yet';

  const resolveEscalation = async (escalationId: string) => {
    const resolutionNote = window.prompt('Enter the supervisor resolution note:');
    if (!resolutionNote?.trim()) return;
    try {
      await apiClient(`/escalations/${escalationId}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ resolution_note: resolutionNote.trim() }),
      });
      setEscalations((current) => current.map((item) => (
        item.escalation_id === escalationId
          ? { ...item, escalation_status: 'resolved' }
          : item
      )));
    } catch (err: any) {
      setFetchError(err?.message || 'Failed to resolve escalation.');
    }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 bg-slate-50 min-h-screen">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Manager Intelligence Hub</h1>
        <p className="text-sm text-gray-500">Real-time aggregated operational analytics and SOP metrics from Snowflake materialized views.</p>
      </div>

      {fetchError && (
        <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-xl shadow-sm">
          <p className="font-semibold text-base">Analytics Data Unavailable</p>
          <p className="text-sm mt-1">{fetchError}</p>
        </div>
      )}

      {/* Overview Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <MetricCard
          title="Total SOP Executions"
          value={fetchError ? 'N/A' : (sopUsage.length > 0 ? totalExecutions : 'No data yet')}
        />
        <MetricCard
          title="Avg. Response Confidence"
          value={fetchError ? 'N/A' : avgConfidence}
        />
        <MetricCard
          title="Confusing Procedures Flagged"
          value={fetchError ? 'N/A' : (confusingProcedures.length > 0 ? confusingProcedures.length : 0)}
        />
        <MetricCard
          title="Department Adoption Rate"
          value={fetchError ? 'N/A' : avgAdoptionRate}
        />
      </div>

      {/* Analytics Dashboard Panels */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Most Confusing Procedures Panel */}
        <div className="p-6 bg-white border border-gray-200 rounded-xl shadow-sm">
          <h2 className="text-lg font-bold text-gray-800 mb-4">Most Confusing Procedures</h2>
          {fetchError ? (
            <p className="text-sm text-red-500 italic">Unable to load procedure escalation metrics.</p>
          ) : confusingProcedures.length === 0 ? (
            <p className="text-sm text-gray-500 italic">No procedures flagged with high escalation rates.</p>
          ) : (
            <ul className="space-y-3 text-sm">
              {confusingProcedures.map((proc, idx) => (
                <li key={idx} className="flex justify-between items-center border-b pb-2 border-gray-100">
                  <span className="font-medium text-gray-700">{proc.sop_title || `SOP #${proc.sop_id}`}</span>
                  <span className="text-red-600 font-semibold">{proc.confusion_rate_pct || 0}% Escalation Rate</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Confidence Score Trends Panel */}
        <div className="p-6 bg-white border border-gray-200 rounded-xl shadow-sm">
          <h2 className="text-lg font-bold text-gray-800 mb-4">Confidence Score Trends</h2>
          {fetchError ? (
            <p className="text-sm text-red-500 italic">Unable to load confidence score trends.</p>
          ) : confidenceTrends.length === 0 ? (
            <div className="h-40 flex items-center justify-center border-2 border-dashed border-gray-200 text-gray-400 rounded-lg text-sm">
              No confidence score trend data logged yet.
            </div>
          ) : (
            <div className="space-y-2">
              {confidenceTrends.slice(0, 5).map((item, idx) => (
                <div key={idx} className="flex justify-between items-center text-xs py-1 border-b border-gray-100">
                  <span className="text-gray-600">{item.metric_date}</span>
                  <span className="font-semibold text-blue-700">{(item.avg_confidence_score * 100).toFixed(1)}% Avg Confidence</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="p-6 bg-white border border-gray-200 rounded-xl shadow-sm">
          <h2 className="text-lg font-bold text-gray-800 mb-4">Frequently Asked Topics</h2>
          {faqs.length === 0 ? (
            <p className="text-sm text-gray-500 italic">No categorized employee questions yet.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {faqs.slice(0, 10).map((item, index) => (
                <li key={`${item.department_id}-${item.query_topic}-${index}`} className="flex justify-between border-b pb-2">
                  <span>{item.query_topic}</span>
                  <span className="text-slate-500">{item.query_count} · {item.department_id}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="p-6 bg-white border border-gray-200 rounded-xl shadow-sm">
          <h2 className="text-lg font-bold text-gray-800 mb-4">Escalations</h2>
          {escalations.length === 0 ? (
            <p className="text-sm text-gray-500 italic">No escalation records.</p>
          ) : (
            <ul className="space-y-3 text-sm">
              {escalations.slice(0, 10).map((item) => (
                <li key={item.escalation_id} className="border-b pb-3">
                  <div className="flex justify-between gap-3">
                    <span className="font-medium">{item.sop_title || 'General Copilot request'}</span>
                    <span className="capitalize text-slate-500">{item.escalation_status}</span>
                  </div>
                  <p className="text-xs text-slate-600 mt-1">{item.escalation_reason}</p>
                  {item.escalation_status !== 'resolved' && (
                    <button
                      onClick={() => resolveEscalation(item.escalation_id)}
                      className="mt-2 text-xs text-blue-700 hover:underline"
                    >
                      Resolve escalation
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
