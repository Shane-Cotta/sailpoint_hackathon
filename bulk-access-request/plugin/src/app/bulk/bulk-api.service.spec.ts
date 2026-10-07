import { TestBed } from '@angular/core/testing';
import { SailpointPluginService } from '@core';

import { DEMO_CONFIG } from '../demo/fixtures';
import { routedPlugin } from '../testing/plugin.testing';
import { BulkApiService, escapeQuery, splitPasted } from './bulk-api.service';

function setup(routes: Record<string, unknown>) {
  const plugin = routedPlugin(routes);
  TestBed.configureTestingModule({ providers: [{ provide: SailpointPluginService, useValue: plugin }] });
  return { api: TestBed.inject(BulkApiService), plugin };
}

const ALAN = '0123456789abcdef0123456789abcdef';

describe('BulkApiService', () => {
  it('starts the workflow through the test endpoint with the trigger contract', async () => {
    const { api, plugin } = setup({ '/v3/workflows/wf-1/test': { workflowExecutionId: 'exec-1' } });
    const input = {
      people: [ALAN], items: [{ id: 'ap-1', type: 'ACCESS_PROFILE' as const, name: 'UCSF Bulk Test Access' }],
      approverId: 'boss', requesterId: 'me', inc: 'INC0012345', justification: 'why',
    };
    await expect(api.submit('wf-1', input)).resolves.toBe('exec-1');
    expect(plugin.post).toHaveBeenCalledWith('/v3/workflows/wf-1/test', { input });
  });

  it('says so when the workflow does not start', async () => {
    const { api } = setup({ '/v3/workflows/': {} });
    await expect(api.submit('wf-1', {} as never)).rejects.toThrow('did not start');
  });

  it('finds the workflow by name unless the config names its ID', async () => {
    const { api } = setup({ '/v3/workflows': [{ id: 'other', name: 'Something else' }, { id: 'wf-9', name: DEMO_CONFIG.workflowName }] });
    await expect(api.workflowId({ ...DEMO_CONFIG, workflowId: null })).resolves.toBe('wf-9');
    await expect(api.workflowId({ ...DEMO_CONFIG, workflowId: 'fixed' })).resolves.toBe('fixed');
    await expect(api.workflowId({ ...DEMO_CONFIG, workflowId: null, workflowName: 'Missing' })).rejects.toThrow('install.py');
  });

  it('resolves pasted IDs, usernames and emails, and reports the rest', async () => {
    const { api } = setup({
      [`/v2025/identities/${ALAN}`]: { id: ALAN, name: 'Alan Bradley', attributes: { displayName: 'Alan Bradley' } },
      '/v2025/identities?': [{ id: 'id-mei', name: 'mei.lin', alias: 'mei.lin', emailAddress: 'mei.lin@example.edu' }],
      '/v3/search': [
        { id: 'id-k1', name: 'andrea.kim', displayName: 'Andrea Kim', email: 'andrea.kim@example.edu' },
        { id: 'id-k2', name: 'akim', displayName: 'Andrea Kim', email: 'ANDREA.KIM@example.edu' },
      ],
      // Identities missing from the search index are found through their accounts.
      '/v3/accounts': [{ identityId: 'id-andrei', name: 'Andrei Popescu', nativeIdentity: 'usr_example01',
        identity: { name: 'Andrei Popescu' }, attributes: { email: 'andrei@example.edu' }, sourceName: 'UCSF SaaS' }],
    });
    const result = await api.resolvePeople([ALAN, 'Mei.Lin@example.edu', 'usr_example01', 'andrea.kim@example.edu', 'nobody']);
    expect(result.resolved.map((p) => p.id)).toEqual([ALAN, 'id-mei', 'id-andrei']);
    expect(result.unresolved).toEqual(['nobody']);
    expect(result.ambiguous).toHaveLength(1);
    expect(result.ambiguous[0].token).toBe('andrea.kim@example.edu');
    expect(result.ambiguous[0].matches.map((m) => m.id).sort()).toEqual(['id-k1', 'id-k2']);
  });

  it('searches identities and accounts, de-duplicated and sorted', async () => {
    const { api, plugin } = setup({
      '/v3/search': [{ id: 'a', displayName: 'Zed', email: 'z@x' }],
      '/v3/accounts': [{ identityId: 'a', name: 'Zed' }, { identityId: 'b', name: 'Amy', identity: { name: 'Amy' } }],
    });
    expect((await api.searchPeople('am')).map((p) => p.name)).toEqual(['Amy', 'Zed']);
    expect(await api.searchPeople('a')).toEqual([]);                      // too short: no call
    expect(plugin.post).toHaveBeenCalledTimes(1);
  });

  it('loads the catalog with repeated `types`, the name filter, and sources', async () => {
    const { api, plugin } = setup({
      '/v3/requestable-objects': [
        { id: 'ap', type: 'ACCESS_PROFILE', name: 'UCSF Bulk Test Access' },
        { id: 'r', type: 'ROLE', name: 'UCSF Role' },
        { id: 'x', type: 'ACCESS_PROFILE', name: 'Other' },
      ],
      '/v3/search': [{ id: 'ap', source: { name: 'UCSF SaaS' } }],
    });
    const options = await api.catalog({ ...DEMO_CONFIG, nameStartsWith: 'UCSF' });
    expect(options.map((o) => o.subLabel)).toEqual(['Access profile · UCSF SaaS', 'Role']);
    const url = plugin.get.mock.calls[0][0] as string;
    expect(url).toContain('types=ACCESS_PROFILE&types=ROLE&types=ENTITLEMENT');
    expect(decodeURIComponent(url)).toContain('name sw "UCSF"');
  });

  it('reports which chosen people already hold or have requested an item', async () => {
    const { api } = setup({
      '/v3/requestable-objects?identity-id=p1': [{ id: 'ap', requestStatus: 'ASSIGNED' }],
      '/v3/requestable-objects?identity-id=p2': [{ id: 'ap', requestStatus: 'AVAILABLE' }],
      '/v3/requestable-objects?identity-id=p3': [{ id: 'ap', requestStatus: 'PENDING' }],
    });
    const found = await api.existingAccess(['p1', 'p2', 'p3'], [{ id: 'ap', type: 'ACCESS_PROFILE', name: 'X' }]);
    expect(found).toEqual(expect.arrayContaining([
      { personId: 'p1', itemId: 'ap', status: 'ASSIGNED' },
      { personId: 'p3', itemId: 'ap', status: 'PENDING' },
    ]));
    expect(found).toHaveLength(2);
  });

  it("loads the user's own bulk approvals with approver details the list leaves out", async () => {
    const row = (id: string, name: string, requester: string, created: string) =>
      ({ id, name: [{ value: name }], status: 'PENDING', requester: { identityID: requester }, createdDate: created });
    const { api, plugin } = setup({
      '/v2025/generic-approvals?': [
        row('a1', 'Bulk access INC0000001', 'me', '2026-10-01'),
        row('a2', 'Bulk access INC0000002', 'someone-else', '2026-10-02'),
        row('a3', 'Quarterly review', 'me', '2026-10-03'),
        row('a4', 'Bulk access INC0000004', 'me', '2026-10-04'),
      ],
      '/v2025/generic-approvals/a1': { approvers: [{ name: 'Aisha Bello' }] },
      '/v2025/generic-approvals/a4': Promise.reject(new Error('boom')),
    });
    const mine = await api.myBulkApprovals('me');
    expect(mine.map((a) => a.id)).toEqual(['a4', 'a1']);                 // newest first, ours only
    expect(mine[1].approvers).toEqual([{ name: 'Aisha Bello' }]);
    expect(mine[0].name?.[0].value).toBe('Bulk access INC0000004');     // detail failed: list row kept
    expect(plugin.get).toHaveBeenCalledTimes(3);
  });

  it('splits pasted lists and escapes search terms', () => {
    expect(splitPasted(' a@x.edu\nb, c;a@x.edu\t\n')).toEqual(['a@x.edu', 'b', 'c']);
    expect(escapeQuery('o"brien (x)')).toBe('o\\"brien \\(x\\)');
  });
});
