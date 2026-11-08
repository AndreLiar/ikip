import type { RetrieveResponse } from '@/lib/types';

import { CitationChip } from './CitationChip';

/** Raw retrieval results (Story 4.4 AC1): ranked chunks + their citations. */
export function SearchResults({ results }: { results: RetrieveResponse }): React.JSX.Element {
  if (results.abstained || results.results.length === 0) {
    return (
      <p className="search-empty" data-testid="search-empty">
        No matching passages.
      </p>
    );
  }
  return (
    <ol className="search-results" data-testid="search-results">
      {results.results.map((r, i) => (
        <li key={i} className="search-result">
          <p className="snippet">{r.content}</p>
          <CitationChip citation={r.citation} />
        </li>
      ))}
    </ol>
  );
}
