import type { AskResponse } from '@/lib/types';

import { CitationChip } from './CitationChip';
import { FeedbackBar } from './FeedbackBar';

/**
 * Renders a grounded answer (Story 4.4 AC2/AC3): per-claim citations, safety-critical
 * flags, surfaced warnings, the explicit abstention state, and the always-present
 * not-certified notice. Never shows unverified content — the API already dropped it.
 * When the answer was persisted (messageId given), shows a feedback bar (Story 4.6).
 */
export function AnswerPanel({
  answer,
  messageId,
}: {
  answer: AskResponse;
  messageId?: string;
}): React.JSX.Element {
  if (answer.status === 'abstained') {
    return (
      <section className="answer answer--abstained" data-testid="abstention" role="status">
        <h2>Insufficient evidence</h2>
        <p>{answer.abstention_reason ?? 'The documentation doesn’t support an answer.'}</p>
        <p className="notice">{answer.not_certified_notice}</p>
      </section>
    );
  }

  return (
    <section className="answer" data-testid="answer">
      {answer.cache_hit ? <span className="badge-cache">cached</span> : null}
      <ul className="claims">
        {answer.claims.map((claim, i) => (
          <li key={i} className={claim.safety_critical ? 'claim claim--safety' : 'claim'}>
            {claim.safety_critical ? (
              <span className="badge-safety" data-testid="safety">
                ⚠ safety
              </span>
            ) : null}
            <span className="claim-text">{claim.text}</span>
            <span className="claim-citations">
              {claim.citations.map((c, j) => (
                <CitationChip key={j} citation={c} />
              ))}
            </span>
          </li>
        ))}
      </ul>

      {answer.warnings.length > 0 ? (
        <div className="warnings" data-testid="warnings">
          <h3>Warnings</h3>
          <ul>
            {answer.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="notice">{answer.not_certified_notice}</p>
      {messageId ? <FeedbackBar messageId={messageId} /> : null}
    </section>
  );
}
