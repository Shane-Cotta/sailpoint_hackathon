# SailPoint UI Plugin Guide

> Framework-agnostic guide for building a SailPoint Identity Security UI plugin and wiring the SDK into your own project. It is intentionally self-contained so both humans and AI coding assistants have full context without external lookups.
>
> Using the Angular starter? See the Angular-specific guide instead (`angular/starter/SAILPOINT_PLUGIN_GUIDE_ANGULAR.md` in the `ui-plugin-templates` repository). You only need the one guide that matches how you started.

## Context for AI assistants

- This project is a **SailPoint UI plugin**: a standalone frontend app that SailPoint Identity Security loads inside a **sandboxed iframe** at a designated UI **slot**.
- The plugin is isolated from the host. It communicates with the host only through the SailPoint UI Plugin SDK, which wraps a `postMessage` protocol (COIP). Do not assume direct DOM, cookie, or network access to the host page.
- Network calls to SailPoint APIs use a **scoped token** limited to the `apiScopes` declared in `sp-ui-plugin.json`. A call to an undeclared scope fails the same way locally as in production.
- `sp-ui-plugin.json` is the source of truth for the plugin's identity and security posture. Treat it as the contract with the backend.
- Build tooling is your framework's own. The SailPoint CLI orchestrates registration and deployment. The CLI does not replace your bundler.

## The configuration file: `sp-ui-plugin.json`

```jsonc
{
    "version": 1,
    "manifest": {
        "alias": "",                    // tenant-unique, path-safe key (lowercase,
                                        // alphanumeric + dashes, 3-63 chars)
        "name": { "en": "" },           // localized display name
        "description": { "en": "" },    // localized description
        "apiScopes": ["sp:scopes:all"], // SailPoint API scopes the plugin may use
        "permissionPolicy": {},         // Permissions-Policy directives
        "iframeAllow": {},              // iframe `allow` directives (object form)
        "contentSecurityPolicies": {},  // CSP directives for the plugin's assets
        "slots": [{ "slotId": "full-page" }]
    },
    "build": {
        "outDir": "./dist/<your-build-output>", // compiled assets uploaded on deploy
        "port": 4200                            // local dev server port
    }
}
```

- **`manifest`** is sent verbatim to the backend. **`build`** is local-only and is not sent to the backend.
- Set **`build.outDir`** to your framework's compiled output directory, and **`build.port`** to the port your local dev server listens on.
- Security fields (`permissionPolicy`, `iframeAllow`, `contentSecurityPolicies`) are declarative — edit them by hand as your plugin needs them. The CLI validates the file against the expected schema before deploying.
- The **alias** is a stable, environment-independent key. The same alias maps to a different plugin instance in each tenant, so you can deploy the same code to staging and production without juggling GUIDs.

### Updating the manifest

The SailPoint CLI generates `sp-ui-plugin.json` when you run `init` (default scaffold or `init --path`). Review the file and edit it as your plugin needs.

| When you edit | What to do |
|---|---|
| After `init`, before `create` | Edit `sp-ui-plugin.json`. Then run `sail ui-plugins create`. |
| After `create` | Edit `sp-ui-plugin.json`. Then run `sail ui-plugins push-manifest` (alias `update`) to send the updated `manifest` section to the tenant. |

The `build` section is local only. It is never sent to the backend. If you change manifest security fields after `create`, run `push-manifest`. Then run `link` again if you need refreshed `devDocumentHeaders` for local dev.

## Quick start (existing project)

Use this checklist when you add plugin support to a project that already exists. The steps apply to any framework and any bundler.

1. Run `sail ui-plugins init --path <dir> --out-dir <build-output> --port <port>` to generate `sp-ui-plugin.json` and this guide. If you do not use the CLI, add `sp-ui-plugin.json` at the project root yourself. Review `build.outDir` and `build.port` and match them to your bundler (see [Updating the manifest](#updating-the-manifest)).
2. Install `@sailpoint/ui-plugin-sdk` and `sailpoint-api-client` (see [SDK setup](#sdk-setup)).
3. Create one SDK singleton. Start `getContext()` once at startup (see [Reference singleton](#reference-singleton)).
4. Expose `status` and `context` through your app's state mechanism (see [Plugin bootstrap contract](#plugin-bootstrap-contract)).
5. Configure the dev server for HTTPS, the correct port, and document headers (see [Dev environment requirements](#dev-environment-requirements)). Configure the production build for relative asset paths (see [Building and deploying](#relative-asset-paths-required-for-upload)).
6. Run `sail ui-plugins create`, then `sail ui-plugins link`. Restart the dev server after header values change.
7. Open SailPoint Identity Security with `?spPluginDev=<alias>` to load your local code in the tenant.

Import SailPoint design tokens when you want host styling (see [Design tokens / theming](#design-tokens--theming)).

## Local development

The SailPoint CLI registers your plugin and links your local server for in-tenant development (see [SailPoint CLI](#sailpoint-cli)). The development loop is:

1. Register the plugin with your tenant.
2. Start your framework's dev server over HTTPS on `build.port`.
3. Link your local server to your identity. Open the returned developer URL (`?spPluginDev=<alias>`). If you are authorized, the host loads your local code inside the live tenant with a local-dev badge. You get a real handshake, a real scoped token, and live data.

Because local dev uses a real scoped token from your declared `apiScopes`, an endpoint you did not declare fails locally the same way it fails in production. Add scopes to `sp-ui-plugin.json` before you need them. If you already ran `create`, run `push-manifest` after you add scopes.

For plugin-document security headers during local dev, see [Local dev document headers](#local-dev-document-headers).

### Expected behavior: standalone vs in-tenant

| How you open the app | Handshake | API calls |
|---|---|---|
| Dev server URL directly (`https://localhost:<port>`) | `failed` (expected) | Do not work |
| SailPoint Identity Security with `?spPluginDev=<alias>` | `ready` | Work with declared scopes |

A failed handshake on the dev server alone is normal. Test API calls only in SailPoint Identity Security with the developer URL from link.

## Dev environment requirements

Every bundler must satisfy the same concerns. The config file names differ.

| Concern | Where it lives | Notes |
|---|---|---|
| Output directory | `sp-ui-plugin.json` `build.outDir` | Must match your production build output |
| Dev port | `sp-ui-plugin.json` `build.port` and dev server config | Values must match |
| HTTPS | Dev server config | SailPoint Identity Security loads plugins from `https://localhost:<port>` |
| Document headers | Dev server config | Copy from `devDocumentHeaders` after create/link |

### HTTPS for local development

SailPoint Identity Security expects your dev server at `https://localhost:<port>`. Most bundlers need explicit HTTPS setup: a plugin, a certificate, or a reverse proxy. Self-signed certificates are common locally. Browser trust warnings are expected.

Read your bundler's HTTPS documentation. Do not assume one flag works in every stack.

**Illustrative Vite example** (not normative). Webpack, Rsbuild, and others follow the same concerns in their own config files:

```javascript
// vite.config.js
import basicSsl from '@vitejs/plugin-basic-ssl';

export default {
  base: './', // production build — relative paths for CDN upload (see Building and deploying)
  plugins: [basicSsl()],
  server: {
    port: 4200, // match sp-ui-plugin.json build.port
    headers: {
      // paste Content-Security-Policy and Permissions-Policy from devDocumentHeaders
    },
  },
};
```

Install `@vitejs/plugin-basic-ssl` if you use this pattern: `npm install -D @vitejs/plugin-basic-ssl`.

## Local dev document headers

The plugin iframe is governed by plugin-document `Content-Security-Policy` and `Permissions-Policy` headers. In production, a SailPoint service, UMS, stamps these on CDN assets. During local development, your dev server must emit the same headers for CSP parity.

**Source of truth for the dev server:** your framework's dev-server configuration (for example, Vite `server.headers` or Angular `angular.json` serve options). `sp-ui-plugin.json` does **not** control dev-server response headers.

### Getting the effective header values

On successful `sail ui-plugins create` or `sail ui-plugins link`, UMS returns `devDocumentHeaders` in the API response:

```json
{
  "devDocumentHeaders": {
    "Content-Security-Policy": "...",
    "Permissions-Policy": "..."
  }
}
```

Inspect this response to see the merged headers your production CDN assets will carry. UMS merges the platform baseline with any author extensions from your manifest. Copy these values into your dev-server config. Do not guess tenant-specific origins such as `https://<your-org>.api.cloud.sailpoint.com`.

**Restart required:** If your dev server is already running when create or link returns new headers, restart it before you test in SailPoint Identity Security.

**Symptom:** If the handshake succeeds but API calls fail with CSP or connect errors, the dev server is likely missing `devDocumentHeaders`. Copy them from the create/link output into your dev server's response headers. Then restart the dev server.

Use the `Content-Security-Policy` and `Permissions-Policy` strings from `devDocumentHeaders`, not placeholder values. For a combined Vite example with HTTPS and headers, see [HTTPS for local development](#https-for-local-development).

### Angular starter (CLI default)

If you scaffolded with the default `sail ui-plugins init` flow (Angular template), the CLI updates `angular.json` automatically. See the [Angular plugin guide](https://github.com/sailpoint-oss/ui-plugin-templates/blob/main/angular/starter/SAILPOINT_PLUGIN_GUIDE_ANGULAR.md) — you do not need to wire headers manually.

### Existing project (`init --path`)

`sail ui-plugins init --path <dir>` adds `sp-ui-plugin.json` and this guide to an existing project but does **not** modify your dev-server config. After create/link, copy `devDocumentHeaders` into your bundler's dev-server settings yourself (see [HTTPS for local development](#https-for-local-development) for a Vite example, or the equivalent for your stack).

### Manifest security fields

`sp-ui-plugin.json` `contentSecurityPolicies` and `permissionPolicy` do **not** directly configure dev-server headers. If you change manifest security fields after `create`, run `push-manifest`. UMS merges those changes with the platform baseline. Then create/link returns updated `devDocumentHeaders` for you to apply to your dev server. On the Angular path, the CLI writes them into `angular.json`.

## Building and deploying

Build your project with your framework's own tooling. Make sure that the output lands in `build.outDir`. Deploy the compiled assets with the SailPoint CLI (see [SailPoint CLI](#sailpoint-cli)). Uploaded assets are hosted immutably on the CDN. Deployment targets the plugin instance bound to your **alias** in the CLI's current tenant context. The same commands promote across environments.

### Relative asset paths (required for upload)

SailPoint Identity Security serves production plugin assets from a CDN URL. That URL is not the root of your dev server. The built HTML, JavaScript, CSS, fonts, and other static files must reference each other with **relative** paths (for example `./main.js`, not `/main.js`). Absolute paths break after upload. The browser requests them from the wrong location and the plugin fails to load.

Configure your **production build** before the first `upload`. This is not a dev-server setting.

| Bundler | Typical setting |
|---|---|
| Vite | `base: './'` in `vite.config.js` |
| Webpack | `output.publicPath: './'` (or `'auto'` where supported) |
| Rsbuild | `output.assetPrefix: './'` |
| Angular | `baseHref: "./"` and `deployUrl: "./"` in `angular.json` build options |

If you use a starter template, these values are already configured. If you used `init --path` on React, Vue, or another stack, set the equivalent in your bundler config. Then run a production build and inspect `index.html`. Script and stylesheet URLs must be relative.

**Symptom:** The plugin iframe is blank, or the browser console shows 404 errors for JS or CSS at paths like `/assets/...` instead of paths next to `index.html`.

## SailPoint CLI

These files are typically placed in your project by the SailPoint CLI (`sail ui-plugins init` or `sail ui-plugins init --path`). The CLI also registers, links, and deploys your plugin. For the authoritative command list, usage, and flags, use the CLI's own help and documentation rather than relying on this guide:

- `sail ui-plugins --help` (and `sail ui-plugins <command> --help`)
- CLI documentation: <https://developer.sailpoint.com/docs/tools/cli>

## SDK setup

Install the runtime SDK. Create **one** instance for the life of the page. Resolve the plugin context **once**. Then read context, call APIs, and subscribe to host events. The SDK is framework-agnostic. The examples below are plain TypeScript. Wrap them in whatever singleton your framework prefers (see [Wrapping the SDK in your framework](#wrapping-the-sdk-in-your-framework)).

### 1. Install

```bash
npm install @sailpoint/ui-plugin-sdk sailpoint-api-client
# or: pnpm add @sailpoint/ui-plugin-sdk sailpoint-api-client
```

Install both packages up front if you plan to use typed API calls. You can add `sailpoint-api-client` later if you start with `sdk.api.get` / `sdk.api.post` only.

### 2. Reference singleton

Create a single SDK instance in one module. Import that module everywhere. Do not construct the SDK inside components that mount more than once.

The SDK resolves the App Shell origin from the iframe context. It uses the `?parentOrigin` query parameter. When available, it reconciles that value with the browser ancestor origin. It falls back to the document referrer. Pass `createSDK({ targetOrigin })` only for tests, mocks, or non-standard embeddings.

App Shell completes one handshake per iframe mount. A second SDK instance sends a fresh readiness request that the host ignores. That instance never finishes initialization.

This reference module illustrates the key invariants every plugin should implement:

```ts
// plugin-sdk.ts
import { createSDK, type PluginContext, type SailPointPluginSDK } from '@sailpoint/ui-plugin-sdk';

type PluginStatus = 'pending' | 'ready' | 'failed';

interface PluginBootstrap {
  sdk: SailPointPluginSDK | null;
  status: PluginStatus;
  context: PluginContext | null;
  ready: Promise<PluginContext>;
}

const SINGLETON_KEY = Symbol.for('@sailpoint/ui-plugin-sdk#singleton');

function createBootstrap(): PluginBootstrap {
  let sdk: SailPointPluginSDK | null = null;
  let ready: Promise<PluginContext>;

  try {
    sdk = createSDK();
    ready = sdk.getContext();
  } catch {
    ready = Promise.reject(new Error('Open the plugin in SailPoint Identity Security with ?spPluginDev=<alias>.'));
    return { sdk: null, status: 'failed', context: null, ready };
  }

  const bootstrap: PluginBootstrap = {
    sdk,
    status: 'pending',
    context: null,
    ready: ready.then((context) => {
      bootstrap.status = 'ready';
      bootstrap.context = context;
      return context;
    }).catch(() => {
      bootstrap.status = 'failed';
      throw new Error('App Shell handshake failed.');
    }),
  };

  return bootstrap;
}

function getBootstrap(): PluginBootstrap {
  const globalRef = globalThis as typeof globalThis & {
    [key: symbol]: PluginBootstrap | undefined;
  };
  const existing = globalRef[SINGLETON_KEY];
  if (existing) {
    return existing;
  }
  const bootstrap = createBootstrap();
  globalRef[SINGLETON_KEY] = bootstrap;
  return bootstrap;
}

export const pluginBootstrap = getBootstrap();
export const sdk = pluginBootstrap.sdk;
export const ready = pluginBootstrap.ready;
```

Cache the bootstrap on `globalThis` with a stable key so hot module reload (HMR) does not create a second SDK after a file save. If `createSDK()` throws outside SailPoint Identity Security, the app can boot with `status: 'failed'` instead of crashing.

### 3. Resolve the plugin context once

The handshake runs on the first `getContext()` call. It returns `tenant`, `user`, `page`, and `slot` context. Start it once during startup and share the promise. API calls depend on this context because the SDK derives your tenant API base from it.

```ts
import { ready, pluginBootstrap } from './plugin-sdk';

// Gate first render or first API call on the shared promise:
const context = await ready;
console.log(context.tenant.org, context.user.displayName, context.page.route);

// Read status anywhere without awaiting again:
console.log(pluginBootstrap.status); // 'pending' | 'ready' | 'failed'
```

### Plugin bootstrap contract

Map this contract to your framework's state primitives (signals, context, stores, and so on). You do not need identical names, but the behavior must match.

| Field | Type | Purpose |
|---|---|---|
| `status` | `'pending' \| 'ready' \| 'failed'` | Handshake lifecycle for UI and guards |
| `context` | plugin context or `null` | Populated when `status` is `ready` |
| `ready` | `Promise<PluginContext>` | Shared handshake promise. Await before API calls. |
| `whenReady()` | same as `ready` | Optional alias for app bootstrap gating only |

Optional helpers that wrap `sdk.api.get` / `sdk.api.post` are common. Keep them thin. Do not start a second handshake inside them.

Components read `status` and `context`. Reserve `whenReady()` / `ready` for app startup gating, not for every component.

### 4. Call the SailPoint API

You can call the API in two ways:

- **`sailpoint-api-client`** — typed API classes and models (recommended when you want IDE help and versioned method names).
- **`sdk.api.get` / `sdk.api.post`** — simple authenticated HTTP when you do not need the full client.

Both use the scoped bearer token from the handshake. Pass a **path suffix to a versioned endpoint**, not a full URL. Requests are limited to the `apiScopes` in `sp-ui-plugin.json`.

#### Before the first API call

- Await `ready` (or your equivalent) before `Configuration.autoconfigure()` or `sdk.api.*`.
- Disable UI that triggers API calls until `status === 'ready'`.
- `Configuration.autoconfigure()` reads `window.sailpointConfig()`. That function exists only after the handshake completes.

#### Typed calls with `sailpoint-api-client`

After the handshake, the UI Plugin SDK registers `window.sailpointConfig()`. That function returns your tenant base URL and a fresh access token. Call `Configuration.autoconfigure()` before you construct an API class:

```ts
import { Configuration } from 'sailpoint-api-client/configuration';
import { TenantApi } from 'sailpoint-api-client/tenant/api';

await ready; // handshake must finish first

const config = await Configuration.autoconfigure();
const api = new TenantApi(config);
const response = await api.getTenantV1();
```

Import from a partition sub-path (for example `sailpoint-api-client/tenant/api`) when you build for the browser. This keeps the bundle smaller than importing from the package root.

> **Angular:** the Angular starter uses `@sailpoint/angular-sdk`, which replaces `sailpoint-api-client` with Angular-native injectable services. See [the Angular plugin guide](https://github.com/sailpoint-oss/ui-plugin-templates/blob/main/angular/starter/SAILPOINT_PLUGIN_GUIDE_ANGULAR.md).

#### Simple calls with the plugin SDK

```ts
await ready;
const identities = await sdk.api.get('/v3/public-identities?limit=10');
await sdk.api.post('/v3/some-resource', { name: 'example' });
```

If you need the raw token for a custom `fetch`, use `sdk.api.getToken()`.

### 5. React to host events

Subscribe only when `pluginBootstrap.status === 'ready'` and `sdk` is set:

```ts
if (!sdk) {
  throw new Error('SDK is not available until the handshake completes.');
}

const stopViewport = sdk.events.onViewportChange(({ width, height }) => {
  // the host viewport changed
});
const stopToken = sdk.events.onTokenUpdate((token) => {
  // a refreshed scoped token was pushed
});
// each subscription returns an unsubscribe function — call it when you're done.
```

### Wrapping the SDK in your framework

Put the reference singleton and bootstrap contract in your framework's idiomatic module:

- **Angular** — a `providedIn: 'root'` service that creates the SDK, resolves `getContext()` in an app initializer, and exposes context as signals. See the [Angular plugin guide](https://github.com/sailpoint-oss/ui-plugin-templates/blob/main/angular/starter/SAILPOINT_PLUGIN_GUIDE_ANGULAR.md).
- **React** — a module singleton plus a context provider that resolves `getContext()` once and shares `status` and `context`.
- **Vue** — a plugin or a Pinia store initialized once at app creation.
- **Svelte** — a store populated once from `getContext()`.
- **No framework** — import `pluginBootstrap`, `sdk`, and `ready` from `plugin-sdk.ts`.

The invariants are the same everywhere: one SDK instance, one shared handshake promise, await before API calls, and HMR-safe caching on `globalThis`.

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| Handshake stuck or times out | Second SDK instance, or page opened outside SailPoint Identity Security | Use one cached singleton. Open SailPoint Identity Security with `?spPluginDev=<alias>`. |
| Handshake `failed` on localhost alone | Expected outside the host iframe | Test API calls only through the developer URL in SailPoint Identity Security |
| API 403 or scope errors | Missing `apiScopes` in `sp-ui-plugin.json` | Add the scope. If you already ran `create`, run `push-manifest`. |
| API blocked by browser (CSP / connect) | Dev server missing document headers | Copy `devDocumentHeaders` into dev server config. Then restart. |
| Worked until save or HMR | New SDK instance after module reload | Cache bootstrap on `globalThis` with `Symbol.for(...)` |
| Typed client CORS errors | Wrong headers or wrong origin | Make sure the handshake is `ready` in SailPoint Identity Security. Use partition sub-path imports (for example `sailpoint-api-client/tenant/api`). |
| Blank iframe or 404 on JS/CSS after upload | Absolute asset paths in production build | Set bundler to emit relative paths (for example Vite `base: './'`). Rebuild and upload. |

## Design tokens / theming

**Component library (Angular):** [PrimeNG](https://primeng.org/) is the chosen component library for Angular UI plugins. It is included in the Angular starter by default.

**Component library (other frameworks):** _TBD._ The Prime family offers framework-specific equivalents ([PrimeReact](https://primereact.org/), [PrimeVue](https://primevue.org/)) that share the same theming model. The SailPoint Design System preset in the Angular starter is built and tested with components in the PrimeNG library; using it with PrimeReact or PrimeVue may work, but it is not officially supported by SailPoint and there may be unexpected theming gaps in certain components. 

**ISC design tokens:** _TBD._ ISC-compatible design tokens and component library theme configuration will be delivered by the SailPoint Design System package. For Angular, `provideSds()` will be a thin wrapper around `providePrimeNG()` that applies the ISC theme preset automatically. Equivalent integration points for other frameworks are TBD alongside the framework starter decisions.

**Dark mode:** The theme supports dark mode under the selector `.spds-dark`. Once the SailPoint Design System package is available, plugins will be configurable to automatically apply this class to sync with the color scheme of the ISC tenant. For early development, plugin authors would apply this class on their iframe's `html` element to view dark mode.

**Icons:** Font Awesome icons are the standard for SailPoint UI plugins across all frameworks. Bundling mechanism _TBD_.

**CSS isolation:** The plugin iframe has its own CSS scope. Any styles, including component library theme styles, must be imported inside the plugin. They are not inherited from the host page.

