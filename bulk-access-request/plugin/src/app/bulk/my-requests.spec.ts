import { DEMO_APPROVALS, DEMO_CONFIG, DEMO_ME, DEMO_REQUESTS } from '../demo/fixtures';
import { executionIdOf, groupByInc, isBulkApproval, statusLabel } from './my-requests';

describe('My bulk requests grouping', () => {
  const groups = groupByInc(DEMO_CONFIG, DEMO_ME.id, DEMO_APPROVALS, DEMO_REQUESTS);

  it('groups approvals and access requests by INC, newest first', () => {
    expect(groups.map((g) => [g.inc, g.status])).toEqual([
      ['INC0048213', 'PENDING'],
      ['INC0047950', 'APPROVED'],
      ['INC0047711', 'REJECTED'],
    ]);
  });

  it('keeps every submission of a re-submitted INC, latest decision first', () => {
    const resubmitted = groups.find((g) => g.inc === 'INC0047711')!;
    expect(resubmitted.submissions.map((s) => s.status)).toEqual(['REJECTED', 'CANCELLED']);
    expect(resubmitted.requests).toEqual([]);
  });

  it('counts the people and items an approved request was filed for', () => {
    const approved = groups.find((g) => g.inc === 'INC0047950')!;
    expect(approved.people).toBe(3);
    expect(approved.items).toBe(2);
    expect(approved.submissions[0].decidedBy).toBe('Carmen Ruiz');
  });

  it("ignores other people's approvals, other approvals, and requests without an INC", () => {
    const foreign = { ...DEMO_APPROVALS[0], requester: { identityID: 'someone-else' } };
    const unrelated = { ...DEMO_APPROVALS[0], name: [{ value: 'Quarterly review' }] };
    expect(groupByInc(DEMO_CONFIG, DEMO_ME.id, [foreign, unrelated], [])).toEqual([]);
    expect(isBulkApproval(unrelated)).toBe(false);
    expect(groups.some((g) => g.requests.some((r) => r.item === 'Zoom - Licensed User'))).toBe(false);
  });

  it('a request with requests but no approval still shows, as Requested', () => {
    const only = groupByInc(DEMO_CONFIG, DEMO_ME.id, [], DEMO_REQUESTS);
    expect(only.map((g) => [g.inc, g.status])).toEqual([['INC0047950', 'REQUESTED']]);
  });

  it('reads the execution ID from the approval and labels statuses', () => {
    expect(executionIdOf(DEMO_APPROVALS[0])).toBe('e0000000-0000-4000-8000-000000000001');
    expect(statusLabel('REJECTED')).toEqual({ label: 'Denied', severity: 'danger' });
  });
});
