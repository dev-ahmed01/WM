import type { CopilotResponse } from './api-client';

/** Export only information already returned to this authorized browser session. */
export function formatEvidenceNote(answer: string, response: CopilotResponse): string {
  const citations = response.citations ?? [];
  const grounded = response.is_grounded && citations.length > 0 && !response.requires_escalation;
  const lines = [
    'WORKMATE · OPERATIONAL EVIDENCE NOTE',
    'Generated locally: ' + new Date().toISOString(),
    'Status: ' + (grounded ? 'Grounded response (review source excerpts)' : 'Unverified / requires human review'),
    'System-reported confidence: ' + Math.round(response.confidence_score * 100) + '% (not a guarantee of correctness)',
    'Escalation: ' + (response.requires_escalation ? 'Required' : 'Not flagged'),
    '',
    'ANSWER',
    answer.trim(),
    '',
    'CITED SOURCE EXCERPTS (' + citations.length + ')',
  ];

  if (citations.length === 0) lines.push('No citations were returned for this answer.');
  citations.forEach((citation, index) => {
    lines.push(
      '',
      '[' + (index + 1) + '] ' + citation.document_title,
      'Source: ' + (citation.source_type === 'reference' ? 'Approved reference' : 'Published workflow'),
      'Version: ' + (citation.version_number ?? 'not supplied'),
      'Section: ' + (citation.section_anchor || 'not supplied'),
      'Step: ' + (citation.step_number ?? 'not supplied'),
      'Citation ID: ' + citation.chunk_id,
      'Excerpt: ' + (citation.excerpt || 'No excerpt supplied'),
    );
  });
  lines.push('', 'This is a point-in-time note, not an approval, audit attestation, or proof of task completion.');
  return lines.join('\n');
}

export function downloadEvidenceNote(answer: string, response: CopilotResponse) {
  const blob = new Blob([formatEvidenceNote(answer, response)], { type: 'text/plain;charset=utf-8' });
  const href = URL.createObjectURL(blob);
  const element = document.createElement('a');
  element.href = href;
  element.download = 'workmate-evidence-' + new Date().toISOString().replace(/[:.]/g, '-') + '.txt';
  document.body.appendChild(element);
  element.click();
  element.remove();
  window.setTimeout(() => URL.revokeObjectURL(href), 1000);
}
