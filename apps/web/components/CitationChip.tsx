import type { Citation } from '@/lib/types';

/**
 * A resolvable citation (FR16): document revision + section + page. "Clickable" in the
 * sense of an actionable reference; opening the source PDF at the cited page is Story 4.5
 * (R2 presigned URL) — deferred, so here it's an inert chip carrying the full reference.
 */
export function CitationChip({ citation }: { citation: Citation }): React.JSX.Element {
  const parts: string[] = [];
  if (citation.revision) parts.push(`rev ${citation.revision}`);
  if (citation.hierarchy_path) parts.push(`§${citation.hierarchy_path}`);
  if (citation.page_start != null) {
    parts.push(
      citation.page_end && citation.page_end !== citation.page_start
        ? `p.${citation.page_start}-${citation.page_end}`
        : `p.${citation.page_start}`,
    );
  }
  const obsolete = citation.is_current === false;
  return (
    <span className="citation" data-testid="citation" title={citation.heading ?? undefined}>
      {parts.join(' · ') || 'source'}
      {obsolete ? <span className="badge-obsolete"> obsolete</span> : null}
    </span>
  );
}
