#!/usr/bin/env python3
"""Offline structural check of a Workflow Studio JSON definition (stdlib only).

Catches the failures the track warns about before you upload:
  * a step whose nextStep points nowhere ("Err: next is not defined")
  * a chain that does not end in a success/End step
  * a variable path that references a step that does not run before it
  * a {{ }} path whose field is not kept by that step's resultSelector
  * a JSONPath written without {{ }} in subject/body (arrives as literal text)
  * the recipient placeholder still in place

Usage: python3 scripts/validate_workflow.py workflow/*.workflow.json
Exit code 0 = no errors (warnings allowed), 1 = errors.
"""
import json
import re
import sys

VAR_RE = re.compile(r"\{\{\s*(\$\.[A-Za-z0-9_.\[\]]+)\s*\}\}")


def step_root(step_key: str) -> str:
    """'Get Identity 1' -> 'getIdentity1', 'Send Email' -> 'sendEmail'."""
    parts = step_key.split()
    head = parts[0].lower() if parts else ""
    return head + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def walk_strings(obj):
    if isinstance(obj, str):
        yield None, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            for _, s in walk_strings(v):
                yield k, s
    elif isinstance(obj, list):
        for v in obj:
            for _, s in walk_strings(v):
                yield None, s


def validate(wf: dict):
    errors, warnings = [], []
    d = wf.get("definition") or {}
    steps = d.get("steps") or {}
    start = d.get("start")
    if not wf.get("name"):
        errors.append("missing workflow name")
    if wf.get("enabled"):
        warnings.append("enabled=true: the create API rejects enabled workflows; create disabled, then enable")
    trig = wf.get("trigger") or {}
    if trig.get("type") != "EVENT" or (trig.get("attributes") or {}).get("id") != "idn:identity-created":
        warnings.append(f"trigger is not EVENT idn:identity-created: {trig}")
    if start not in steps:
        errors.append(f"start step {start!r} not in steps")
        return errors, warnings

    # Walk the chain (this track is linear; choice steps follow choiceList/defaultStep).
    order, seen, frontier = [], set(), [start]
    while frontier:
        k = frontier.pop(0)
        if k in seen:
            continue
        seen.add(k)
        order.append(k)
        s = steps[k]
        nexts = []
        if s.get("type") in ("success", "failure"):
            continue
        if s.get("type") == "choice":
            nexts += [c.get("nextStep") for c in s.get("choiceList", [])] + [s.get("defaultStep")]
        else:
            nexts.append(s.get("nextStep"))
        for n in nexts:
            if not n:
                errors.append(f"step {k!r} has no nextStep (UI error: 'Err: next is not defined')")
            elif n not in steps:
                errors.append(f"step {k!r} -> {n!r} which does not exist")
            else:
                frontier.append(n)
    unreachable = set(steps) - seen
    if unreachable:
        warnings.append(f"unreachable steps: {sorted(unreachable)}")
    if not any(steps[k].get("type") == "success" for k in seen):
        errors.append("no reachable success (End) step")

    # Variable references: each must be $.trigger or a step that runs earlier.
    roots = {step_root(k): k for k in steps}
    position = {k: i for i, k in enumerate(order)}
    for k in order:
        s = steps[k]
        attrs = s.get("attributes") or {}
        refs = []
        for c in s.get("choiceList", []):
            if isinstance(c.get("variableA.$"), str):
                refs.append(("choice.variableA", c["variableA.$"]))
        for ak, av in attrs.items():
            if ak == "resultSelector":
                continue
            if ak.endswith(".$") and isinstance(av, str):
                refs.append((ak, av))
            for _, sv in walk_strings({ak: av}):
                refs += [(ak, m) for m in VAR_RE.findall(sv)]
                if ak in ("subject", "body"):
                    stripped = VAR_RE.sub("", sv)
                    if "$." in stripped:
                        errors.append(f"{k}.{ak}: JSONPath outside {{{{ }}}} will be sent as literal text")
        for ak, path in refs:
            root = path[2:].split(".")[0].split("[")[0]
            if root == "trigger":
                continue
            src = roots.get(root)
            if src is None:
                errors.append(f"{k}.{ak}: {path} references unknown step root {root!r}")
            elif position.get(src, 1 << 30) >= position[k]:
                errors.append(f"{k}.{ak}: {path} references {src!r}, which does not run before {k!r}")
            else:
                sel = (steps[src].get("attributes") or {}).get("resultSelector")
                if sel and not any(path == p or path.startswith(p + ".") for p in sel):
                    warnings.append(f"{k}.{ak}: {path} not in {src!r} resultSelector (may resolve empty)")
        if s.get("actionId") == "sp:send-email":
            rl = attrs.get("recipientEmailList")
            if rl is None and "recipientEmailList.$" not in attrs and "recipientId.$" not in attrs:
                errors.append(f"{k}: send-email has no recipient")
            if isinstance(rl, list) and any("REPLACE_WITH" in r for r in rl):
                warnings.append(f"{k}: recipient is still the placeholder {rl}; set your own address")
            for req in ("subject", "body"):
                if not attrs.get(req):
                    errors.append(f"{k}: send-email missing {req}")
    return errors, warnings


def main(paths):
    rc = 0
    for p in paths:
        with open(p) as f:
            wf = json.load(f)
        errors, warnings = validate(wf)
        print(f"{p}: {'OK' if not errors else 'FAIL'} ({len(errors)} errors, {len(warnings)} warnings)")
        for e in errors:
            print("  ERROR  ", e)
        for w in warnings:
            print("  warning", w)
        rc |= bool(errors)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["workflow/identity-onboarding.workflow.json"]))
