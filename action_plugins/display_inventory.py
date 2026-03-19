#!/usr/bin/python
# -*- coding: utf-8 -*-
# Version: 3.3.1

# Copyright: (c) 2024, Your Name
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

"""
Action plugin for display_inventory.

Runs entirely on the CONTROLLER so the full Ansible Python package
(InventoryManager, VariableManager, DataLoader) is always available.
The companion stub in library/display_inventory.py is never executed
on a remote host — this plugin intercepts the task first.
"""

import fnmatch
import json
import os
from datetime import datetime

from ansible.plugins.action import ActionBase
from ansible.parsing.dataloader import DataLoader
from ansible.inventory.manager import InventoryManager
from ansible.vars.manager import VariableManager
from ansible.errors import AnsibleError


# ---------------------------------------------------------------------------
# Ansible magic keys that are not useful to display
# ---------------------------------------------------------------------------
_MAGIC_KEYS = frozenset({
    "omit",
    "ansible_playbook_python",
    "groups",
    "hostvars",
    "vars",
    "inventory_dir",
    "inventory_file",
    "inventory_hostname",
    "inventory_hostname_short",
    "playbook_dir",
})


# ---------------------------------------------------------------------------
# Inventory loading
# ---------------------------------------------------------------------------

def _load_inventory(sources):
    loader = DataLoader()
    inventory = InventoryManager(loader=loader, sources=sources)
    var_manager = VariableManager(loader=loader, inventory=inventory)
    return loader, inventory, var_manager


# ---------------------------------------------------------------------------
# Variable helpers
# ---------------------------------------------------------------------------

def _host_vars(host, var_manager):
    """Return the full merged variable set for a host, minus magic keys."""
    magic = var_manager.get_vars(host=host)
    return {k: v for k, v in magic.items() if k not in _MAGIC_KEYS}


def _host_vars_raw(host):
    """Return only variables explicitly set on the host object (export mode)."""
    return dict(host.vars)


def _group_vars(group):
    """Return variables explicitly set on a group."""
    return dict(group.vars)


# ---------------------------------------------------------------------------
# Pattern filtering
# ---------------------------------------------------------------------------

def _matches_pattern(hostname, pattern):
    """
    Return True if *hostname* matches *pattern*.

    Supports shell-style wildcards (fnmatch): *, ?, [seq].
    A plain string with no wildcards requires an exact match.
    """
    if not pattern:
        return True
    return fnmatch.fnmatch(hostname, pattern)


# ---------------------------------------------------------------------------
# Rendering: mode=list
# ---------------------------------------------------------------------------

def _build_list(inventory, var_manager, show_vars=False, show_hostvars=False,
                export=False, group=None, pattern=None):
    """
    Build the dict that ansible-inventory --list emits.

    Parameters
    ----------
    show_vars     : include group-level vars in each group block
    show_hostvars : populate _meta.hostvars with each host's full variable set
    export        : use raw host/group vars only (no inheritance)
    group         : restrict output to hosts in this group name
    pattern       : further filter hosts by fnmatch pattern
    """
    # Apply group scope
    if group:
        if group not in inventory.groups:
            raise AnsibleError("Group '{0}' not found in inventory.".format(group))
        inventory.subset(group)

    # Build active host set, optionally filtered by pattern
    active_hosts = {
        h.name: h
        for h in inventory.get_hosts()
        if _matches_pattern(h.name, pattern)
    }

    result = {"_meta": {"hostvars": {}}}

    for grp in inventory.groups.values():
        entry = {}

        # Directly-assigned hosts only (group.hosts, not get_hosts())
        direct_hosts = sorted(
            h.name for h in grp.hosts if h.name in active_hosts
        )
        if direct_hosts:
            entry["hosts"] = direct_hosts

        children = sorted(c.name for c in grp.child_groups)
        if children:
            entry["children"] = children

        if show_vars:
            gv = _group_vars(grp)
            if gv:
                entry["vars"] = gv

        result[grp.name] = entry

    # Populate _meta.hostvars
    for hostname, host in active_hosts.items():
        if show_hostvars:
            hv = _host_vars_raw(host) if export else _host_vars(host, var_manager)
            result["_meta"]["hostvars"][hostname] = hv
        else:
            result["_meta"]["hostvars"][hostname] = {}

    return result


# ---------------------------------------------------------------------------
# Rendering: --host (single host variable lookup)
# ---------------------------------------------------------------------------

def _build_host(hostname, inventory, var_manager):
    """Return the variable dict for a single named host, or None if not found."""
    host = inventory.get_host(hostname)
    if host is None:
        return None
    return _host_vars(host, var_manager)


# ---------------------------------------------------------------------------
# Rendering: mode=graph
# ---------------------------------------------------------------------------

def _build_graph(inventory, var_manager, show_vars=False, group=None, pattern=None):
    """
    Render the inventory as an indented text tree.

    Parameters
    ----------
    show_vars : show group and host variables inline
    group     : root the graph at this group instead of 'all'
    pattern   : only show hosts whose names match this fnmatch pattern
    """
    # Choose the root group early so we can validate before touching inventory
    root_name = group if group else "all"
    root = inventory.groups.get(root_name)
    if root is None:
        raise AnsibleError("Group '{0}' not found in inventory.".format(root_name))

    # Collect every host reachable from the root (recursive), then apply the
    # pattern filter.  We deliberately avoid inventory.subset() because it
    # rewrites internal inventory state and makes get_hosts() return nothing
    # for the subsequent group walk.
    def _all_hosts_in_group(grp, seen=None):
        if seen is None:
            seen = set()
        for h in grp.get_hosts():
            seen.add(h.name)
        for child in grp.child_groups:
            _all_hosts_in_group(child, seen)
        return seen

    reachable    = _all_hosts_in_group(root)
    active_hosts = {n for n in reachable if _matches_pattern(n, pattern)}

    lines = []

    def _render_group(grp, depth=0):
        pad = "  " * depth
        lines.append("{0}|--@{1}:".format(pad, grp.name))

        if show_vars:
            for k, v in sorted(_group_vars(grp).items()):
                lines.append("{0}  |--{{{1} = {2}}}".format(pad, k, v))

        for child in sorted(grp.child_groups, key=lambda g: g.name):
            _render_group(child, depth + 1)

        for host in sorted(grp.get_hosts(), key=lambda h: h.name):
            if host.name not in active_hosts:
                continue
            lines.append("{0}  |--{1}".format(pad, host.name))
            if show_vars:
                for k, v in sorted(_host_vars(host, var_manager).items()):
                    lines.append("{0}    |--{{{1} = {2}}}".format(pad, k, v))

    lines.append("@{0}:".format(root_name))

    for child in sorted(root.child_groups, key=lambda g: g.name):
        _render_group(child, depth=0)

    # Hosts sitting directly on the root.
    # For "all": skip hosts already shown inside a named child group.
    # For a named group: show its direct hosts (root.hosts) unconditionally.
    if root_name == "all":
        child_group_names = {c.name for c in root.child_groups} - {"ungrouped"}
        for host in sorted(root.get_hosts(), key=lambda h: h.name):
            if host.name not in active_hosts:
                continue
            if not {g.name for g in host.groups}.intersection(child_group_names):
                lines.append("|--{0}".format(host.name))
                if show_vars:
                    for k, v in sorted(_host_vars(host, var_manager).items()):
                        lines.append("  |--{{{0} = {1}}}".format(k, v))
    else:
        for host in sorted(root.hosts, key=lambda h: h.name):
            if host.name not in active_hosts:
                continue
            lines.append("|--{0}".format(host.name))
            if show_vars:
                for k, v in sorted(_host_vars(host, var_manager).items()):
                    lines.append("  |--{{{0} = {1}}}".format(k, v))

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def _to_json(data):
    return json.dumps(data, indent=4, sort_keys=True, default=str)


def _to_yaml(data):
    import yaml
    return yaml.dump(data, default_flow_style=False, allow_unicode=True)


def _to_toml(data):
    try:
        import tomli_w
        return tomli_w.dumps(data)
    except ImportError:
        pass
    try:
        import toml
        return toml.dumps(data)
    except ImportError:
        raise AnsibleError(
            "TOML output requires 'tomli_w' or 'toml' on the controller. "
            "Install with: pip install tomli_w"
        )


def _serialise(data, output_format):
    """Serialise *data* dict to 'json', 'yaml', or 'toml'."""
    if output_format == "toml":
        return _to_toml(data)
    if output_format == "yaml":
        return _to_yaml(data)
    return _to_json(data)


# ---------------------------------------------------------------------------
# Action plugin
# ---------------------------------------------------------------------------

class ActionModule(ActionBase):
    """
    Controller-side action plugin for display_inventory.

    Parameters accepted
    -------------------
    mode          : 'list' or 'graph'   (required unless 'host' is set)
    host          : str                 (mutually exclusive with mode)
    show_vars     : bool  (default False) — include group/host vars in output
    show_hostvars : bool  (default False) — populate _meta.hostvars in list mode
    export        : bool  (default False) — raw vars only, no inheritance
    export_file   : path                  — write output to this file
    group         : str                   — scope to a specific group
    pattern       : str                   — fnmatch filter on host names
    output_format : 'json'|'yaml'|'toml'  (default 'json')
    inventory     : str                   — override inventory source
    """

    TRANSFERS_FILES = False
    _VALID_ARGS = frozenset({
        "mode", "host",
        "show_vars", "show_hostvars", "export", "export_file",
        "group", "pattern",
        "output_format",
        "inventory",
    })

    def run(self, tmp=None, task_vars=None):
        if task_vars is None:
            task_vars = {}

        result = super(ActionModule, self).run(tmp, task_vars)
        result.update(changed=False, skipped=False)

        args = self._task.args

        # ── Validate mode vs host ─────────────────────────────────────────────
        mode = args.get("mode")
        host_arg = args.get("host")

        if mode and host_arg:
            result["failed"] = True
            result["msg"] = "'mode' and 'host' are mutually exclusive."
            return result

        if not mode and not host_arg:
            result["failed"] = True
            result["msg"] = (
                "One of 'mode' (choices: list, graph) or 'host' must be specified."
            )
            return result

        if mode and mode not in ("list", "graph"):
            result["failed"] = True
            result["msg"] = (
                "Invalid mode '{0}'. Choose 'list' or 'graph'.".format(mode)
            )
            return result

        # ── output_format validation ──────────────────────────────────────────
        output_format = args.get("output_format", "json")
        if output_format not in ("json", "yaml", "toml"):
            result["failed"] = True
            result["msg"] = (
                "Invalid output_format '{0}'. Choose 'json', 'yaml', or 'toml'.".format(
                    output_format
                )
            )
            return result

        # ── Resolve inventory sources ─────────────────────────────────────────
        if args.get("inventory"):
            sources = [args["inventory"]]
        else:
            sources = task_vars.get("ansible_inventory_sources") or []

        if not sources:
            result["failed"] = True
            result["msg"] = (
                "No inventory sources found. Provide the 'inventory' parameter "
                "or ensure ansible_inventory_sources is populated."
            )
            return result

        result["sources_used"] = sources

        # ── Check mode ────────────────────────────────────────────────────────
        if self._play_context.check_mode:
            result["msg"] = "Check mode: would load inventory from: {0}".format(sources)
            return result

        # ── Load inventory on the controller ─────────────────────────────────
        try:
            loader, inventory, var_manager = _load_inventory(sources)
        except Exception as exc:
            result["failed"] = True
            result["msg"] = "Failed to load inventory: {0}".format(str(exc))
            return result

        # ── Collect parameters ────────────────────────────────────────────────
        show_vars     = bool(args.get("show_vars",     False))
        show_hostvars = bool(args.get("show_hostvars", False))
        export        = bool(args.get("export",        False))
        group         = args.get("group")  or None
        pattern       = args.get("pattern") or None
        export_file   = args.get("export_file") or None

        # ── Execute ───────────────────────────────────────────────────────────
        output_str    = ""
        inventory_data = None

        try:
            if mode == "list":
                inventory_data = _build_list(
                    inventory, var_manager,
                    show_vars=show_vars,
                    show_hostvars=show_hostvars,
                    export=export,
                    group=group,
                    pattern=pattern,
                )
                output_str = _serialise(inventory_data, output_format)

            elif mode == "graph":
                output_str = _build_graph(
                    inventory, var_manager,
                    show_vars=show_vars,
                    group=group,
                    pattern=pattern,
                )

            elif host_arg:
                inventory_data = _build_host(host_arg, inventory, var_manager)
                if inventory_data is None:
                    result["failed"] = True
                    result["msg"] = "Host '{0}' not found in inventory.".format(host_arg)
                    return result
                output_str = _serialise(inventory_data, output_format)

        except AnsibleError:
            raise
        except Exception as exc:
            result["failed"] = True
            result["msg"] = "Error rendering inventory: {0}".format(str(exc))
            return result

        result["output"] = output_str
        if inventory_data is not None:
            result["inventory_data"] = inventory_data

        # ── Write export file ─────────────────────────────────────────────────
        if export_file:
            # Derive the correct extension from the chosen output format
            ext_map = {"json": ".json", "yaml": ".yml", "toml": ".toml"}
            ext = ext_map.get(output_format, ".json")

            # Stamp YYYYMMDD_HHMM before the extension so every export is unique
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            base, _ = os.path.splitext(export_file)
            stamped_path = "{0}_{1}{2}".format(base, timestamp, ext)

            try:
                with open(stamped_path, "w") as fh:
                    fh.write(output_str)
                result["export_file"] = stamped_path
            except IOError as exc:
                result["failed"] = True
                result["msg"] = "Could not write '{0}': {1}".format(
                    stamped_path, str(exc)
                )
                return result

        return result
