import { Component, computed, effect, inject, signal } from '@angular/core';
import { SailpointPluginService } from '@core';
import { Paginator } from '@sailpoint/angular-sdk';
import { IdentitiesService, type Identity } from '@sailpoint/angular-sdk/identities';
import { MessageModule } from 'primeng/message';
import { TagModule } from 'primeng/tag';
import { firstValueFrom } from 'rxjs';
import { FormsModule } from '@angular/forms';
import { SelectModule } from 'primeng/select';
import { SkeletonModule } from 'primeng/skeleton';
import { AvatarModule } from 'primeng/avatar';
import { TableModule } from 'primeng/table';
import { TeamAccessService, type OpenReview } from './team-access/team-access.service';
import {
  buildMember,
  commonAccess,
  teamFlags,
  type Flag,
  type FlagType,
  type Member,
  type SearchDocument,
  type Severity,
} from './team-access/team-flags';
/** One entry in the manager dropdown. */
interface ManagerOption {
  id: string;
  name: string;
}
const FLAG_LABELS: Record<FlagType, string> = {
  leaver_risk: 'Leaver risk',
  privileged_access: 'Privileged',
  unique_access: 'Unique access',
  access_outlier: 'Access outlier',
  missing_baseline: 'Missing baseline',
  no_roles: 'No roles',
};
@Component({
  selector: 'app-root',
  imports: [AvatarModule, FormsModule, MessageModule, SelectModule, SkeletonModule, TableModule, TagModule],
  providers: [IdentitiesService],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly plugin = inject(SailpointPluginService);
  private readonly identitiesSvc = inject(IdentitiesService);
  private readonly teamAccess = inject(TeamAccessService);
  /** Every identity the page has loaded. Everything else is derived from this. */
  protected readonly identities = signal<Identity[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  /** The manager the user picked in the dropdown. */
  protected readonly selectedManagerId = signal('');
  /**
   * The dropdown options. Every identity carries a managerRef, so the set of
   * managers is the set of distinct managerRef values in the loaded list.
   */
  protected readonly managers = computed<ManagerOption[]>(() => {
    const byId = new Map<string, ManagerOption>();
    for (const identity of this.identities()) {
      const ref = identity.managerRef;
      if (ref?.id && ref.name) {
        byId.set(ref.id, { id: ref.id, name: ref.name });
      }
    }
    return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name));
  });
  /** The direct reports of the selected manager. */
  protected readonly reports = computed<Identity[]>(() => {
    const managerId = this.selectedManagerId();
    if (!managerId) {
      return [];
    }
    return this.identities().filter((identity) => identity.managerRef?.id === managerId);
  });
  // ── Team Access Radar ─────────────────────────────────────────────────────
  /** Search documents for the selected manager's team (with nested access). */
  protected readonly teamDocs = signal<SearchDocument[]>([]);
  protected readonly teamLoading = signal(false);
  protected readonly teamError = signal('');
  protected readonly reviews = signal<OpenReview[]>([]);
  protected readonly reviewsError = signal('');
  /** Same rules as the MCP server's review_team_access (see team-flags.ts). */
  protected readonly members = computed<Member[]>(() => this.teamDocs().map(buildMember));
  protected readonly flags = computed<Flag[]>(() => teamFlags(this.members()));
  protected readonly baseline = computed(() => commonAccess(this.members()));
  protected readonly severityCounts = computed(() => {
    const counts: Record<Severity, number> = { high: 0, medium: 0, low: 0 };
    for (const flag of this.flags()) counts[flag.severity] += 1;
    return counts;
  });
  protected readonly flaggedPeople = computed(() => new Set(this.flags().map((f) => f.identity)).size);
  /** Flag types per person, for the team table. */
  protected readonly flagsByPerson = computed(() => {
    const byName = new Map<string, Flag[]>();
    for (const flag of this.flags()) {
      byName.set(flag.identity, [...(byName.get(flag.identity) ?? []), flag]);
    }
    return byName;
  });
  private teamRequest = 0;
  private requested = false;
  constructor() {
    // Wait for the App Shell handshake, then load once.
    effect(() => {
      if (this.plugin.apiReady() && !this.requested) {
        this.requested = true;
        void this.loadIdentities();
      }
    });
  }
  protected async loadIdentities(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const identities = await firstValueFrom(
        Paginator.paginate(
          (params) => this.identitiesSvc.listIdentitiesV1(params),
          { sorters: 'name' },
        ),
      );
      this.identities.set(identities);
    } catch (err) {
      this.error.set(this.formatApiError(err));
    } finally {
      this.loading.set(false);
    }
  }
  /** Runs when the user picks a manager. p-select hands us the option's value. */
  protected onManagerChange(managerId: string | null): void {
    this.selectedManagerId.set(managerId ?? '');
    void this.loadTeam(managerId ?? '');
  }
  /** Fetch the team (with access) and the manager's open reviews, in parallel. */
  protected async loadTeam(managerId: string): Promise<void> {
    const request = ++this.teamRequest;
    this.teamDocs.set([]);
    this.reviews.set([]);
    this.teamError.set('');
    this.reviewsError.set('');
    if (!managerId || !this.plugin.apiReady()) {
      return;
    }
    this.teamLoading.set(true);
    const [team, reviews] = await Promise.allSettled([
      this.teamAccess.directReports(managerId),
      this.teamAccess.openReviews(managerId),
    ]);
    if (request !== this.teamRequest) {
      return; // the user picked someone else meanwhile
    }
    if (team.status === 'fulfilled') {
      this.teamDocs.set(team.value ?? []);
    } else {
      this.teamError.set(this.formatApiError(team.reason));
    }
    if (reviews.status === 'fulfilled') {
      this.reviews.set(reviews.value);
    } else {
      this.reviewsError.set(this.formatApiError(reviews.reason));
    }
    this.teamLoading.set(false);
  }
  /** p-tag severity for a flag severity. */
  protected flagSeverity(severity: Severity): 'danger' | 'warn' | 'info' {
    return severity === 'high' ? 'danger' : severity === 'medium' ? 'warn' : 'info';
  }
  /** Short human label for a flag type. */
  protected flagLabel(type: FlagType): string {
    return FLAG_LABELS[type] ?? type;
  }
  /** The flags raised for one person, for the team table. */
  protected personFlags(name: string): Flag[] {
    return this.flagsByPerson().get(name) ?? [];
  }
  protected progress(review: OpenReview): string {
    if (!review.decisionsTotal) return 'not started';
    const pct = Math.round((100 * review.decisionsMade) / review.decisionsTotal);
    return `${review.decisionsMade}/${review.decisionsTotal} decisions (${pct}%)`;
  }
  /** Reads one identity attribute out of the untyped attributes map. */
  protected attr(identity: Identity, key: string): string {
    const attributes = identity.attributes as Record<string, unknown> | undefined;
    const value = attributes?.[key];
    return typeof value === 'string' && value ? value : '-';
  }
  /** Initials for the avatar, so "Jean Bartik" becomes "JB". */
  protected initials(name: string): string {
    return name
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0].toUpperCase())
      .join('');
  }
  /** Maps an identity type onto a p-tag severity: employees are green, contractors are yellow. */
  protected typeSeverity(type: string): 'success' | 'warn' | 'secondary' {
    switch (type.toUpperCase()) {
      case 'EMPLOYEE':
        return 'success';
      case 'CONTRACTOR':
        return 'warn';
      default:
        return 'secondary';
    }
  }
  private formatApiError(err: unknown): string {
    return err instanceof Error ? `${err.name}: ${err.message}` : String(err);
  }
}
