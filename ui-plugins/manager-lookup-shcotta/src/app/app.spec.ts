import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { App } from './app';
import { SailpointPluginService } from '@core';
import type { Identity } from '@sailpoint/angular-sdk/identities';

/** Minimal identity fixture: only the fields the page reads. */
function identity(id: string, name: string, managerId?: string, managerName?: string): Identity {
  return {
    id,
    name,
    emailAddress: `${id}@acme.com`,
    attributes: { department: 'Engineering', type: 'EMPLOYEE' },
    managerRef: managerId ? { type: 'IDENTITY', id: managerId, name: managerName } : null,
  } as unknown as Identity;
}

describe('App (Team Access Radar)', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        // Stub the plugin service so no real SDK / App Shell handshake runs.
        // apiReady() is false, so the component never calls the API in tests.
        {
          provide: SailpointPluginService,
          useValue: {
            context: signal({
              tenant: { org: 'acme' },
              user: { displayName: 'Test User', email: 'test@acme.com' },
              page: { route: 'https://acme.identitysoon.com/ui/plugin/manager-lookup-shcotta', subPath: '' },
            }),
            status: signal('ready'),
            apiReady: () => false,
          },
        },
      ],
    }).compileComponents();
  });

  it('renders the header with tenant and user from the plugin context', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.page__title')?.textContent).toContain('Team Access Radar');
    expect(el.querySelector('.page__meta')?.textContent).toContain('Test User');
  });

  it('derives a de-duplicated, sorted manager list and the selected manager\'s reports', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    app['identities'].set([
      identity('m1', 'Zoe Manager'),
      identity('m2', 'Adam Manager'),
      identity('e1', 'Eve', 'm1', 'Zoe Manager'),
      identity('e2', 'Bob', 'm1', 'Zoe Manager'),
      identity('e3', 'Cat', 'm2', 'Adam Manager'),
    ]);

    expect(app['managers']().map((m) => m.name)).toEqual(['Adam Manager', 'Zoe Manager']);

    app['onManagerChange']('m1');
    expect(app['reports']().map((r) => r.name).sort()).toEqual(['Bob', 'Eve']);

    app['onManagerChange'](null);
    expect(app['reports']()).toEqual([]);
  });

  it('builds initials and maps identity types to tag severities', () => {
    const app = TestBed.createComponent(App).componentInstance;
    expect(app['initials']('Jean Bartik')).toBe('JB');
    expect(app['typeSeverity']('employee')).toBe('success');
    expect(app['typeSeverity']('CONTRACTOR')).toBe('warn');
    expect(app['typeSeverity']('-')).toBe('secondary');
  });

  it('flags the team with the shared rules and counts severities', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    const base = [
      { type: 'ENTITLEMENT', name: 'All_Users', source: { name: 'AD' } },
      { type: 'ENTITLEMENT', name: 'campusAccess', source: { name: 'AD' } },
    ];
    app['teamDocs'].set([
      {
        id: 'b', displayName: 'Brandon', accessCount: 3,
        access: [...base, { type: 'ENTITLEMENT', name: 'AccountingGeneral', source: { name: 'AD' }, privileged: true }],
      },
      { id: 'n', displayName: 'Nicole', accessCount: 2, access: base },
      { id: 'a', displayName: 'Adam', accessCount: 2, access: base },
    ]);

    expect(app['flags']()[0]).toMatchObject({ severity: 'high', type: 'privileged_access', identity: 'Brandon' });
    expect(app['severityCounts']()).toEqual({ high: 1, medium: 1, low: 0 });
    expect(app['flaggedPeople']()).toBe(1);
    expect(app['personFlags']('Brandon').map((f) => f.type)).toEqual(['privileged_access', 'unique_access']);
    expect(app['baseline']().map((b) => b.access)).toEqual(['AD: All_Users', 'AD: campusAccess']);
    expect(app['flagLabel']('missing_baseline')).toBe('Missing baseline');
    expect(app['flagSeverity']('high')).toBe('danger');
  });

  it('shows review progress as decisions made', () => {
    const app = TestBed.createComponent(App).componentInstance;
    expect(app['progress']({ id: 'c', name: 'Q4', decisionsMade: 3, decisionsTotal: 12 })).toBe('3/12 decisions (25%)');
    expect(app['progress']({ id: 'c', name: 'Q4', decisionsMade: 0, decisionsTotal: 0 })).toBe('not started');
  });

  it('emails the manager for a flag and shows the outcome', async () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    const service = app['teamAccess'];
    const notify = vi.spyOn(service, 'notifyManager').mockResolvedValue('Completed');
    app['teamDocs'].set([{ id: 'b-id', displayName: 'Brandon', access: [] }]);
    const flag = { severity: 'high' as const, type: 'leaver_risk' as const, identity: 'Brandon', reason: 'x' };

    await app['notify'](flag);
    expect(notify).toHaveBeenCalledWith('b-id', flag);
    expect(app['notifyState']()[app['flagKey'](flag)]).toBe('sent');

    notify.mockResolvedValue('Failed');
    await app['notify'](flag);
    expect(app['notifyState']()[app['flagKey'](flag)]).toContain('no email was sent');

    await app['notify']({ ...flag, identity: 'Nobody' });
    expect(app['notifyState']()['Nobody|leaver_risk']).toContain("Could not find Nobody's identity id");
  });
});
