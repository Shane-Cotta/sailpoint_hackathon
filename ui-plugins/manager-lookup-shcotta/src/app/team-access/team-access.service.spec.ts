import { TestBed } from '@angular/core/testing';
import { SailpointPluginService } from '@core';
import { NOTIFY_WORKFLOW_ID, notifyInput, TeamAccessService } from './team-access.service';
import type { Flag } from './team-flags';

const FLAG: Flag = {
  severity: 'high',
  type: 'privileged_access',
  identity: 'Brandon.Mason',
  reason: 'Holds 2 privileged item(s), 1 of which no one else on the team has.',
  items: ['Active Directory: AccountingGeneral'],
};

function setup(statuses: string[]) {
  const post = vi.fn().mockResolvedValue({ workflowExecutionId: 'exec-1' });
  const get = vi.fn();
  for (const status of statuses) get.mockResolvedValueOnce({ status });
  TestBed.configureTestingModule({
    providers: [{ provide: SailpointPluginService, useValue: { post, get } }],
  });
  return { service: TestBed.inject(TeamAccessService), post, get };
}

describe('TeamAccessService.notifyManager', () => {
  it('builds the workflow input the MCP server also sends', () => {
    expect(notifyInput('id-1', FLAG)).toEqual({
      identityId: 'id-1',
      flag: 'privileged_access (high)',
      detail:
        'Holds 2 privileged item(s), 1 of which no one else on the team has. ' +
        'Items: Active Directory: AccountingGeneral. (sent from Team Access Radar)',
    });
  });

  it('starts the Radar workflow through the test endpoint and waits for it to finish', async () => {
    const { service, post, get } = setup(['Running', 'Completed']);
    const result = await service.notifyManager('id-1', FLAG, { pollMs: 1 });

    expect(result).toBe('Completed');
    expect(post).toHaveBeenCalledWith(`/v3/workflows/${NOTIFY_WORKFLOW_ID}/test`, {
      input: notifyInput('id-1', FLAG),
    });
    expect(get).toHaveBeenLastCalledWith('/v3/workflow-executions/exec-1');
  });

  it('reports a failed run instead of claiming success', async () => {
    const { service } = setup(['Failed']);
    expect(await service.notifyManager('id-1', FLAG, { pollMs: 1 })).toBe('Failed');
  });

  it('says "Running" when the workflow is still going at the timeout', async () => {
    const { service } = setup(['Running', 'Running', 'Running', 'Running']);
    expect(await service.notifyManager('id-1', FLAG, { pollMs: 1, timeoutMs: 3 })).toBe('Running');
  });
});
