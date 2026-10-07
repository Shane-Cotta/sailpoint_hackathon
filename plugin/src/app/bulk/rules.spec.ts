// Mirrors core/tests/test_core.py (the rules and config sections), so the
// plugin and the Python core refuse exactly the same requests.
import { DEFAULT_CONFIG, parseRuntimeConfig, RuntimeConfigError, type RuntimeConfig } from './runtime-config';
import { catalogOptions, clip, extractInc, incIsValid, justificationMax, validateRequest } from './rules';

/**
 * What plugin/install.py writes for config/bulk-access.example.json (pytest checks that
 * the committed public/bulk-access.config.json equals it). Inlined, because install.py
 * overwrites that file in a build copy with the tenant's own values.
 */
const committed = {
  prefix: 'ACME',
  mode: 'dry-run',
  workflowName: 'ACME Bulk Access Request (Plugin)',
  workflowId: null,
  incPattern: '^INC\\d{7}$',
  incMessage: 'Enter a ServiceNow incident number: INC followed by 7 digits, e.g. INC0012345.',
  incExample: 'INC0012345',
  peopleMax: 50,
  itemsMax: 25,
  catalogTypes: ['ACCESS_PROFILE', 'ROLE', 'ENTITLEMENT'],
  nameStartsWith: null,
  launcherName: 'ACME Bulk Access Request',
};

const EXAMPLE: RuntimeConfig = parseRuntimeConfig(committed);

function cfgWith(overrides: Partial<RuntimeConfig>): RuntimeConfig {
  return parseRuntimeConfig({ ...committed, ...overrides });
}

describe('runtime config', () => {
  it('the example config loads in dry-run with the core defaults', () => {
    expect(EXAMPLE.mode).toBe('dry-run');
    expect(EXAMPLE.incPattern).toBe('^INC\\d{7}$');
    expect(EXAMPLE.itemsMax).toBe(25);
    expect(EXAMPLE.peopleMax).toBe(50);
    expect(EXAMPLE.catalogTypes).toEqual(['ACCESS_PROFILE', 'ROLE', 'ENTITLEMENT']);
    expect(EXAMPLE.workflowName).toMatch(/Bulk Access Request \(Plugin\)$/);
  });

  it.each([
    [{ incPattern: '([' }, 'regular expression'],
    [{ incExample: 'CHG123' }, 'does not match'],
    [{ catalogTypes: ['GROUP'] }, 'catalogTypes'],
    [{ itemsMax: 26 }, 'itemsMax'],
    [{ peopleMax: 0 }, 'peopleMax'],
  ])('rejects a bad config with a useful message (%o)', (override, fragment) => {
    expect(() => parseRuntimeConfig({ ...committed, ...override })).toThrow(RuntimeConfigError);
    expect(() => parseRuntimeConfig({ ...committed, ...override })).toThrow(fragment);
  });

  it('falls back to the defaults for missing keys', () => {
    expect(parseRuntimeConfig({})).toEqual(DEFAULT_CONFIG);
  });
});

describe('rules (core/bulkaccess/rules.py)', () => {
  it('validates the INC with the configured pattern', () => {
    expect(incIsValid(EXAMPLE, 'INC0012345')).toBe(true);
    expect(incIsValid(EXAMPLE, ' INC0012345 ')).toBe(true);
    expect(incIsValid(EXAMPLE, 'INC12345')).toBe(false);
    expect(incIsValid(EXAMPLE, '')).toBe(false);
    const custom = cfgWith({ incPattern: '^(INC|RITM)\\d{7}$', incExample: 'RITM0000001' });
    expect(incIsValid(custom, 'RITM0000001')).toBe(true);
  });

  it('lists every problem with a request', () => {
    const problems = validateRequest(EXAMPLE, { requesterId: 'me', approverId: 'me', people: [], items: [], inc: 'nope' });
    expect(problems).toContain('Choose at least one person.');
    expect(problems).toContain('Choose at least one access item.');
    expect(problems).toContain('The approver must be someone other than you.');
    expect(problems).toContain(EXAMPLE.incMessage);
    const ok = validateRequest(EXAMPLE, {
      requesterId: 'me', approverId: 'boss', people: ['p1'],
      items: [{ id: 'a', type: 'ACCESS_PROFILE' }], inc: 'INC0012345',
    });
    expect(ok).toEqual([]);
  });

  it('enforces the limits, the allowed types and a chosen approver', () => {
    const cfg = cfgWith({ peopleMax: 2, itemsMax: 1, catalogTypes: ['ROLE'] });
    const problems = validateRequest(cfg, {
      requesterId: 'me', approverId: null, people: ['a', 'b', 'c'],
      items: [{ id: 'x', type: 'ACCESS_PROFILE' }, { id: 'y', type: 'ROLE' }], inc: 'INC0012345',
    });
    expect(problems).toEqual([
      'Choose at most 2 people.',
      'Choose at most 1 access items.',
      'One of the chosen items is not an allowed type.',
      'Choose an approver.',
    ]);
  });

  it('builds catalog options that carry full access objects and respect the filters', () => {
    const cfg = cfgWith({ catalogTypes: ['ACCESS_PROFILE'], nameStartsWith: 'ACME' });
    const opts = catalogOptions(cfg, [
      { id: '1', type: 'ACCESS_PROFILE', name: 'ACME Bulk Test Access', source: { name: 'ACME SaaS' } },
      { id: '2', type: 'ACCESS_PROFILE', name: 'Sales Regional - AD' },
      { id: '3', type: 'ROLE', name: 'ACME Role' },
    ]);
    expect(opts.map(({ label, subLabel, value }) => ({ label, subLabel, value }))).toEqual([
      { label: 'ACME Bulk Test Access', subLabel: 'Access profile · ACME SaaS',
        value: { id: '1', type: 'ACCESS_PROFILE', name: 'ACME Bulk Test Access' } },
    ]);
  });

  it('takes sources looked up separately and sorts by name', () => {
    const opts = catalogOptions(EXAMPLE, [
      { id: 'b', type: 'ENTITLEMENT', name: 'beta' },
      { id: 'a', type: 'ROLE', name: 'Alpha' },
    ], { b: 'Active Directory' });
    expect(opts.map((o) => o.subLabel)).toEqual(['Role', 'Entitlement · Active Directory']);
  });

  it('clips long text like rules.clip', () => {
    expect(clip('a  b\n c', 10)).toBe('a b c');
    expect(clip('abcdefghij', 5)).toBe('abcd…');
  });

  it('keeps "<INC>: <justification>" within the approval comment limit', () => {
    expect(justificationMax('INC0012345')).toBe(150 - 2 - 10);
    expect(justificationMax('', 'INC0012345')).toBe(138);
  });

  it('finds the INC in access request comments and approval names', () => {
    expect(extractInc(EXAMPLE, 'INC0012345 | Bulk access request by admin.user | Approved by Aisha')).toBe('INC0012345');
    expect(extractInc(EXAMPLE, 'Bulk access INC0099999')).toBe('INC0099999');
    expect(extractInc(EXAMPLE, 'no ticket here INC12')).toBeNull();
    expect(extractInc(EXAMPLE, null)).toBeNull();
  });
});

describe('assignedApproverNames', () => {
  it('shows who was asked, not the admin who decided on their behalf', async () => {
    const { assignedApproverNames } = await import('./bulk-api.service');
    expect(assignedApproverNames({ assignedTo: [{ name: 'Aisha Bello' }], approvers: [{ name: 'admin.user' }] })).toEqual(['Aisha Bello']);
    expect(assignedApproverNames({ approvers: [{ name: 'admin.user' }] })).toEqual(['admin.user']);
    // decided by an admin on the approver's behalf: SailPoint records a reassignment
    expect(assignedApproverNames({ assignedTo: null, approvers: [{ name: 'admin.user' }],
      reassignmentHistory: [{ reassignedFrom: { name: 'Aisha Bello' } }] })).toEqual(['Aisha Bello']);
  });
});
