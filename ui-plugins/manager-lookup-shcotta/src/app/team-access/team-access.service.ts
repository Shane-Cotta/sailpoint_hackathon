import { inject, Injectable } from '@angular/core';
import { SailpointPluginService } from '@core';
import { directReportsSearch, type SearchDocument } from './team-flags';

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
