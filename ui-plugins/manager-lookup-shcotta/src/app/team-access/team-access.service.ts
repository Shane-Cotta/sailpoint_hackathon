import { inject, Injectable } from '@angular/core';
import { SailpointPluginService } from '@core';
import { directReportsSearch, type Flag, type SearchDocument } from './team-flags';

/**
 * "UCSF Flagged Report to Manager (Radar)": looks up the person and their
 * manager and emails the manager (in this demo tenant, the demo inbox). It is a
 * copy of the workflow the MCP server's notify_manager triggers, generated from
 * the same definition (identity-workflows/scripts/build_workflow.py).
 *
 * The plugin starts it through the workflow *test* endpoint as the signed-in
 * user, because a browser plugin can't hold the external trigger's OAuth
 * secret. Consequences: the workflow must stay DISABLED, and the user needs
 * rights to test workflows (hack.day is ORG_ADMIN). A production version would
 * route this through a small backend or a Launcher with a form instead.
 */
export const NOTIFY_WORKFLOW_ID = '7326ad5b-0113-49d8-94e0-81f821712a50';
const FINAL_STATUSES = new Set(['Completed', 'Failed', 'Canceled']);

/** One open certification, trimmed to what the page shows. */
export interface OpenReview {
  id: string;
  name: string;
  campaign?: string;
  due?: string;
  decisionsMade: number;
  decisionsTotal: number;
}

/**
 * The two API calls behind Team Access Radar, made with the plugin's scoped
 * token as the signed-in user:
 *
 *  - POST /v3/search: a manager's direct reports with their nested access
 *    (the same query the MCP server's review_team_access makes);
 *  - GET /v3/certifications: open certifications the manager must review.
 */
@Injectable({ providedIn: 'root' })
export class TeamAccessService {
  private readonly plugin = inject(SailpointPluginService);

  directReports(managerId: string): Promise<SearchDocument[]> {
    return this.plugin.post<SearchDocument[]>('/v3/search?limit=250', directReportsSearch(managerId));
  }

  /**
   * Email the flagged person's manager about one flag, and wait (briefly) for the
   * workflow to finish so the page can say whether the email actually went out.
   */
  async notifyManager(
    identityId: string,
    flag: Flag,
    opts: { timeoutMs?: number; pollMs?: number } = {},
  ): Promise<NotifyResult> {
    const { timeoutMs = 20000, pollMs = 1500 } = opts;
    const started = await this.plugin.post<{ workflowExecutionId?: string }>(
      `/v3/workflows/${NOTIFY_WORKFLOW_ID}/test`,
      { input: notifyInput(identityId, flag) },
    );
    const executionId = started?.workflowExecutionId;
    if (!executionId) {
      throw new Error('The workflow did not start (no execution id returned).');
    }
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, pollMs));
      const execution = await this.plugin.get<{ status?: string }>(
        `/v3/workflow-executions/${encodeURIComponent(executionId)}`,
      );
      if (execution?.status && FINAL_STATUSES.has(execution.status)) {
        return execution.status as NotifyResult;
      }
    }
    return 'Running';
  }

  async openReviews(managerId: string): Promise<OpenReview[]> {
    const params = new URLSearchParams({
      'reviewer-identity': managerId,
      filters: 'completed eq false',
      limit: '20',
    });
    const certs = await this.plugin.get<Record<string, unknown>[]>(`/v3/certifications?${params}`);
    return (certs ?? []).map(toOpenReview);
  }
}

export type NotifyResult = 'Completed' | 'Failed' | 'Canceled' | 'Running';

/** What the workflow receives: `{identityId, flag, detail}`. */
export function notifyInput(identityId: string, flag: Flag): Record<string, string> {
  const items = flag.items?.length ? ` Items: ${flag.items.join(', ')}.` : '';
  return {
    identityId,
    flag: `${flag.type} (${flag.severity})`,
    detail: `${flag.reason}${items} (sent from UCSF Team Access Radar)`,
  };
}

export function toOpenReview(cert: Record<string, unknown>): OpenReview {
  const campaign = cert['campaign'] as Record<string, unknown> | undefined;
  return {
    id: String(cert['id'] ?? ''),
    name: String(cert['name'] ?? 'Certification'),
    campaign: typeof campaign?.['name'] === 'string' ? (campaign['name'] as string) : undefined,
    due: typeof cert['due'] === 'string' ? (cert['due'] as string) : undefined,
    decisionsMade: Number(cert['decisionsMade'] ?? 0),
    decisionsTotal: Number(cert['decisionsTotal'] ?? 0),
  };
}
