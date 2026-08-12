interface CopilotPresentationOptions {
  spokenAnswer?: string | null;
  sopDetails?: string | null;
}

export interface CopilotPresentation {
  displayText: string;
  spokenText: string;
  sopDetails?: string;
}

const EVIDENCE_FIELD = /(?:^|\s\|\s)([A-Za-z][A-Za-z _]+):\s*/g;

function evidenceValue(content: string, fieldName: string) {
  const fields = [...content.matchAll(EVIDENCE_FIELD)];
  const field = fields.find((match) => match[1].trim().toLowerCase() === fieldName);
  if (field?.index == null) return '';
  const valueStart = field.index + field[0].length;
  const following = fields.find((match) => (match.index ?? 0) > field.index!);
  return content.slice(valueStart, following?.index ?? content.length).trim();
}

function removeInternalCode(value: string) {
  return value.replace(/^(?:STEP|RULE)_[A-Z0-9_-]+\s+/, '').trim();
}

/**
 * Keeps operational guidance conversational while isolating source metadata.
 * The legacy parsing also makes already-persisted metadata dumps safe to view
 * and listen to without rewriting conversation history.
 */
export function presentCopilotMessage(
  content: string,
  options: CopilotPresentationOptions = {},
): CopilotPresentation {
  let displayText = content.trim();
  let derivedDetails: string | undefined;

  const legacyExtract = displayText.match(
    /^Verified extract from '([^']+)' \(v(\d+), step ([^)]+)\):\s*([\s\S]*)$/i,
  );
  if (legacyExtract) {
    const serializedEvidence = legacyExtract[4];
    const instruction = removeInternalCode(evidenceValue(serializedEvidence, 'instructions'));
    const rule = removeInternalCode(evidenceValue(serializedEvidence, 'rules'));
    displayText = instruction || rule || 'I found verified organizational guidance for this request.';
    derivedDetails = `SOP: ${legacyExtract[1]} | version ${legacyExtract[2]} | step ${legacyExtract[3]}`;
  }

  const legacyUsing = displayText.match(/^Using\s+(.+?)\s+\(([^)]+)\)\.\s*([\s\S]*)$/i);
  if (legacyUsing) {
    displayText = legacyUsing[3].trim();
    derivedDetails = `SOP: ${legacyUsing[1]} | ${legacyUsing[2]}`;
  }

  const legacyGuidance = displayText.match(
    /^Verified guidance from workflow step ([^:]+):\s*([\s\S]*?)(?:\s+This answers your question without changing your recorded position at step \d+\.)?$/i,
  );
  if (legacyGuidance) {
    displayText = legacyGuidance[2].trim();
    derivedDetails = derivedDetails ?? `Workflow step ${legacyGuidance[1]}`;
  }

  const spokenText = options.spokenAnswer?.trim() || displayText;
  const sopDetails = options.sopDetails?.trim() || derivedDetails;

  return { displayText, spokenText, sopDetails };
}
