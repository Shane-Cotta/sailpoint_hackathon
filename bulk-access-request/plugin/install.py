#!/usr/bin/env python3
"""Install (or update) the UI plugin deployment of Bulk Access Request.

    python plugin/install.py --config config/<tenant>.json --dry-run   # print every body; change nothing
    python plugin/install.py --config config/<tenant>.json             # workflow + runtime config
    python plugin/install.py --config config/<tenant>.json --deploy    # ...then build and upload the plugin

What it does, idempotently and by prefixed name:
  1. Creates or updates the DISABLED workflow "<prefix> Bulk Access Request (Plugin)",
     owned by the PAT's identity (or `owner` from the config). The plugin starts it
     through the workflow test endpoint, so it must stay disabled.
  2. Writes public/bulk-access.config.json (workflow name and ID, INC rule, limits,
     catalog filter) and sp-ui-plugin.json (alias and name from the config).
  3. With --deploy: `npm run build`, then `sail ui-plugins create --private` (first
     time only, push-manifest after that) and `sail ui-plugins upload`.
     --workdir builds another copy of this folder (one that has node_modules); the
     generated files are then written there instead of here.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pluginlib as lib
from pluginlib import TenantError, config_mod, definitions


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True, help="config/<tenant>.json")
    ap.add_argument("--dry-run", action="store_true", help="print every JSON body; change nothing")
    ap.add_argument("--deploy", action="store_true", help="also build the plugin and upload it with the SailPoint CLI")
    ap.add_argument("--workdir", default=str(lib.PLUGIN_DIR),
                    help="Angular project to build and upload (default: this folder)")
    ap.add_argument("--public", action="store_true",
                    help="with --deploy on first create: visible to everyone, not just you (default: --private)")
    a = ap.parse_args(argv)

    cfg = config_mod.load(a.config)
    tenant = lib.Tenant.from_env(cfg.env_file)
    me = lib.whoami(tenant)
    owner_id = cfg.owner_id or me["id"]
    owner_name = me.get("name") if owner_id == me["id"] else None
    print(f"Tenant {tenant.tenant_name} · prefix {cfg.prefix!r} · mode {cfg.mode} · owner {owner_name or owner_id}")

    body = lib.plugin_workflow(cfg, owner_id, owner_name)
    existing = lib.find_workflow(tenant, cfg.plugin_workflow_name)
    workdir = Path(a.workdir).resolve()

    if a.dry_run:
        print(f"\n== Workflow ({'PUT ' + lib.WORKFLOWS + '/' + existing['id'] if existing else 'POST ' + lib.WORKFLOWS}) ==")
        print(definitions.pretty(body))
        print(f"\n== {lib.RUNTIME_CONFIG} ==\n{definitions.pretty(lib.runtime_config(cfg, (existing or {}).get('id')))}")
        print(f"\n== {lib.MANIFEST} ==\n{definitions.pretty(lib.manifest(cfg))}")
        if a.deploy:
            print(f"\n== Deploy (in {workdir}) ==\nnpm run build\n"
                  f"sail ui-plugins create {'--private' if not a.public else ''}  (only if alias {cfg.plugin_alias!r} is new)\n"
                  "sail ui-plugins push-manifest\nsail ui-plugins upload")
        print("\nDry run: nothing was changed.")
        return 0

    # 1. Workflow (always disabled)
    if existing:
        if existing.get("enabled"):
            tenant.call("PATCH", f"{lib.WORKFLOWS}/{existing['id']}",
                        [{"op": "replace", "path": "/enabled", "value": False}],
                        content_type="application/json-patch+json")
        wf = tenant.call("PUT", f"{lib.WORKFLOWS}/{existing['id']}", body)
        print(f"Workflow updated: {wf['id']}  {cfg.plugin_workflow_name}  (disabled, mode {cfg.mode})")
    else:
        wf = tenant.call("POST", lib.WORKFLOWS, body)
        print(f"Workflow created: {wf['id']}  {cfg.plugin_workflow_name}  (disabled, mode {cfg.mode})")

    # 2. Runtime config + manifest, in the project that gets built
    lib.write_json(workdir / lib.RUNTIME_CONFIG, lib.runtime_config(cfg, wf["id"]))
    lib.write_json(workdir / lib.MANIFEST, lib.manifest(cfg))
    print(f"Wrote {workdir / lib.RUNTIME_CONFIG} and {workdir / lib.MANIFEST}")

    # 3. Build and upload
    if a.deploy:
        if not (workdir / "node_modules").exists():
            raise TenantError(0, f"{workdir} has no node_modules. Run `npx -y npm@11 install` there first.")
        print("Building (npm run build)…")
        subprocess.run(["npm", "run", "build"], cwd=workdir, check=True, stdout=subprocess.DEVNULL)
        plugin = lib.find_plugin(cfg, workdir)
        if plugin:
            lib.sail(cfg, ["ui-plugins", "push-manifest"], workdir)
            print(f"Plugin manifest pushed: {plugin.get('id')}  alias {cfg.plugin_alias}")
        else:
            args = ["ui-plugins", "create"] + ([] if a.public else ["--private"])
            print(lib.sail(cfg, args, workdir).stdout.strip())
        print(lib.sail(cfg, ["ui-plugins", "upload"], workdir).stdout.strip())
        plugin = lib.find_plugin(cfg, workdir) or {}
        ui = tenant.base_url.replace(".api.", ".")
        print(f"Plugin deployed: {ui}/ui/plugin/{plugin.get('id', '<id>')}")

    print("\nDone." + ("" if cfg.live else "  (dry-run mode: approvals run, nothing is requested)")
          + "\nOnly users who may test workflows (ORG_ADMIN) can submit from the plugin; "
            f"everyone else uses the '{cfg.launcher_name}' Launcher.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (config_mod.ConfigError, TenantError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as exc:   # npm or sail missing
        print(f"ERROR: {exc}. Install Node.js/npm and the SailPoint CLI (sail 2.7+).", file=sys.stderr)
        sys.exit(1)
