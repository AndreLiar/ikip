'use client';

import { useState } from 'react';

/**
 * Rate / flag an assistant answer (Story 4.6 AC2). Posts to the BFF, which proxies to
 * POST /api/v1/messages/{id}/feedback. Only shown when the answer has a persisted
 * message id. Feedback is retrievable for failure analysis (AC3).
 */
export function FeedbackBar({ messageId }: { messageId: string }): React.JSX.Element {
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState(false);

  async function send(body: { rating?: number; flagged?: boolean }, label: string): Promise<void> {
    setError(false);
    try {
      const resp = await fetch(`/api/feedback/${messageId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(String(resp.status));
      setSent(label);
    } catch {
      setError(true);
    }
  }

  if (sent) {
    return (
      <p className="feedback feedback--done" data-testid="feedback-done" role="status">
        Thanks — recorded ({sent}).
      </p>
    );
  }

  return (
    <div className="feedback" data-testid="feedback">
      <span>Was this helpful?</span>
      <button
        type="button"
        aria-label="helpful"
        onClick={() => void send({ rating: 1 }, 'helpful')}
      >
        👍
      </button>
      <button
        type="button"
        aria-label="not helpful"
        onClick={() => void send({ rating: -1 }, 'not helpful')}
      >
        👎
      </button>
      <button
        type="button"
        aria-label="flag issue"
        onClick={() => void send({ flagged: true, rating: -1 }, 'flagged')}
      >
        🚩 Report
      </button>
      {error ? (
        <span className="error" role="alert">
          couldn’t send
        </span>
      ) : null}
    </div>
  );
}
