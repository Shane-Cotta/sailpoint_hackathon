import shared from '../../../../../shared/team-flag-cases.json';
import {
  accessLabel,
  buildMember,
  commonAccess,
  directReportsSearch,
  teamFlags,
  type SearchDocument,
} from './team-flags';

/**
 * Parity with the MCP server. shared/team-flag-cases.json is generated from the
 * Python reference implementation (shared/make_flag_cases.py) and also run by
 * tests/test_flag_parity.py, so passing here means the plugin and the chat tools
 * flag the same people for the same reasons.
 */
describe('team flags: parity with the MCP server', () => {
  for (const testCase of shared.cases) {
    it(testCase.name, () => {
      const members = (testCase.documents as SearchDocument[]).map(buildMember);
      expect(teamFlags(members)).toEqual(testCase.expected_flags);
      expect(commonAccess(members)).toEqual(testCase.expected_baseline);
    });
  }
});

describe('team flags: helpers', () => {
  it('labels entitlements with their source, other access by name', () => {
    expect(accessLabel({ type: 'ENTITLEMENT', name: 'Domain Admins', source: { name: 'AD' } })).toBe(
      'AD: Domain Admins',
    );
    expect(accessLabel({ type: 'ROLE', displayName: 'Sales Rep', name: 'sales-rep' })).toBe('Sales Rep');
  });

  it('builds a search for one manager’s reports with nested access', () => {
    const body = directReportsSearch('abc"123');
    expect(body['query']).toEqual({ query: 'manager.id:"abc\\"123"' });
    expect(body['includeNested']).toBe(true);
  });
});

describe('team access service mapping', () => {
  it('trims a certification to what the page shows', async () => {
    const { toOpenReview } = await import('./team-access.service');
    expect(
      toOpenReview({
        id: 'c1',
        name: 'Identity Access Review for Douglas.Flores',
        campaign: { name: 'HackDay demo' },
        due: '2026-10-19T23:59:59Z',
        decisionsMade: 0,
        decisionsTotal: 29,
      }),
    ).toEqual({
      id: 'c1',
      name: 'Identity Access Review for Douglas.Flores',
      campaign: 'HackDay demo',
      due: '2026-10-19T23:59:59Z',
      decisionsMade: 0,
      decisionsTotal: 29,
    });
  });
});
