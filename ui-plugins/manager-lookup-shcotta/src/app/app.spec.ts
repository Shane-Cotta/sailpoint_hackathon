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

describe('App (manager lookup)', () => {
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
    expect(el.querySelector('.page__title')?.textContent).toContain('Manager Reports Search');
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
});
