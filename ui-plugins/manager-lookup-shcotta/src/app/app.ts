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
/** One entry in the manager dropdown. */
interface ManagerOption {
  id: string;
  name: string;
}
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
