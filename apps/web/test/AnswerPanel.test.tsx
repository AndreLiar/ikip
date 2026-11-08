import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AnswerPanel } from '@/components/AnswerPanel';
import type { AskResponse } from '@/lib/types';

const NOTICE = 'AI-generated summary, not a certified manufacturer instruction.';

function answered(over: Partial<AskResponse> = {}): AskResponse {
  return {
    status: 'answered',
    answer: 'A Pod is the smallest deployable unit. [E1]',
    claims: [
      {
        text: 'A Pod is the smallest deployable unit.',
        safety_critical: false,
        citations: [
          {
            chunk_id: 'c1',
            document_id: 'd1',
            document_version_id: 'v1',
            revision: 'A',
            is_current: true,
            section_id: 's1',
            heading: 'Pods',
            hierarchy_path: '1.1',
            page_start: 142,
            page_end: 142,
            score: 0.9,
          },
        ],
      },
    ],
    warnings: [],
    abstention_reason: null,
    not_certified_notice: NOTICE,
    cache_hit: false,
    ...over,
  };
}

describe('AnswerPanel', () => {
  it('renders claims with citations and the not-certified notice', () => {
    render(<AnswerPanel answer={answered()} />);
    expect(screen.getByText(/smallest deployable unit/)).toBeInTheDocument();
    expect(screen.getByTestId('citation')).toHaveTextContent('rev A');
    expect(screen.getByTestId('citation')).toHaveTextContent('p.142');
    expect(screen.getByText(NOTICE)).toBeInTheDocument();
  });

  it('flags safety-critical claims and surfaces warnings', () => {
    const a = answered({
      claims: [
        {
          text: 'De-energize before servicing.',
          safety_critical: true,
          citations: [],
        },
      ],
      warnings: ['claim only partially supported: De-energize before servicing.'],
    });
    render(<AnswerPanel answer={a} />);
    expect(screen.getByTestId('safety')).toBeInTheDocument();
    expect(screen.getByTestId('warnings')).toHaveTextContent('partially supported');
  });

  it('shows the abstention state with its reason', () => {
    const a = answered({
      status: 'abstained',
      answer: null,
      claims: [],
      abstention_reason: 'insufficient evidence',
    });
    render(<AnswerPanel answer={a} />);
    expect(screen.getByTestId('abstention')).toHaveTextContent('Insufficient evidence');
    expect(screen.getByText('insufficient evidence')).toBeInTheDocument();
    // the not-certified notice is present even when abstaining
    expect(screen.getByText(NOTICE)).toBeInTheDocument();
  });

  it('marks an obsolete cited version', () => {
    const a = answered();
    a.claims[0]!.citations[0]!.is_current = false;
    render(<AnswerPanel answer={a} />);
    expect(screen.getByTestId('citation')).toHaveTextContent('obsolete');
  });
});
