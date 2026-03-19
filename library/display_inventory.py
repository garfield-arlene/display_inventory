#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2024, Your Name
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: display_inventory
short_description: Display inventory information using Ansible's Python API
version_added: "3.3.1"
version: "3.3.1"
description:
  - Displays Ansible inventory in various formats, mirroring C(ansible-inventory).
  - All work is performed on the controller by the companion action plugin
    (C(action_plugins/display_inventory.py)) — nothing is executed on remote hosts.
options:
  mode:
    description:
      - Display mode. C(list) outputs hosts/groups as structured data.
        C(graph) renders a hierarchy tree.
      - Mutually exclusive with C(host).
    type: str
    choices: [list, graph]
  host:
    description:
      - Show variables for this specific host.
      - Mutually exclusive with C(mode).
    type: str
  show_vars:
    description:
      - Include group-level variables in the output.
      - In C(graph) mode, group and host variables are printed inline.
      - In C(list) mode, group vars appear in each group block.
    type: bool
    default: false
  show_hostvars:
    description:
      - Populate C(_meta.hostvars) with each host's full variable set.
      - Only meaningful with C(mode=list).
      - Keeping this C(false) (the default) speeds up large inventories.
    type: bool
    default: false
  export:
    description:
      - Use only the variables explicitly set on each host or group object,
        without inheriting from parent groups. Mirrors C(ansible-inventory --export).
      - Only meaningful with C(mode=list) or C(show_hostvars=true).
    type: bool
    default: false
  export_file:
    description:
      - Write the rendered output to this file path on the controller.
      - Works with all modes.
    type: path
  group:
    description:
      - Limit output to hosts that belong to this group.
      - In C(graph) mode this group becomes the root of the tree.
    type: str
  pattern:
    description:
      - Filter displayed hosts to those whose names match this shell-style
        wildcard pattern (C(fnmatch) — supports C(*), C(?), C([seq])).
      - Example: C(web*) matches C(web1), C(webserver), etc.
    type: str
  output_format:
    description:
      - Serialisation format for C(list) and C(host) output.
      - C(graph) output is always plain text.
    type: str
    choices: [json, yaml, toml]
    default: json
  inventory:
    description:
      - Override the inventory source (file path or comma-separated host list).
      - Defaults to the sources already in use by the current play.
    type: str
notes:
  - The action plugin runs on the controller — no remote Python dependencies needed.
  - TOML output requires C(tomli_w) or C(toml) installed on the controller.
  - Use C(delegate_to: localhost) and C(run_once: true).
author:
  - Your Name (@yourhandle)
'''

EXAMPLES = r'''
# ── mode: list ────────────────────────────────────────────────────────────────

- name: List full inventory as JSON
  display_inventory:
    mode: list
  delegate_to: localhost
  run_once: true

- name: List inventory as YAML
  display_inventory:
    mode: list
    output_format: yaml
  delegate_to: localhost
  run_once: true

- name: List inventory with group vars shown
  display_inventory:
    mode: list
    show_vars: true
  delegate_to: localhost
  run_once: true

- name: List inventory with full hostvars populated
  display_inventory:
    mode: list
    show_hostvars: true
  delegate_to: localhost
  run_once: true

- name: List a specific group only
  display_inventory:
    mode: list
    group: webservers
  delegate_to: localhost
  run_once: true

- name: List hosts matching a pattern
  display_inventory:
    mode: list
    pattern: "web*"
  delegate_to: localhost
  run_once: true

- name: Save full inventory to a file
  display_inventory:
    mode: list
    show_hostvars: true
    export_file: /tmp/inventory_snapshot.json
  delegate_to: localhost
  run_once: true

# ── mode: graph ───────────────────────────────────────────────────────────────

- name: Show inventory graph
  display_inventory:
    mode: graph
  delegate_to: localhost
  run_once: true

- name: Show graph with variables
  display_inventory:
    mode: graph
    show_vars: true
  delegate_to: localhost
  run_once: true

- name: Graph a specific group
  display_inventory:
    mode: graph
    group: webservers
  delegate_to: localhost
  run_once: true

- name: Graph hosts matching a pattern
  display_inventory:
    mode: graph
    pattern: "db*"
  delegate_to: localhost
  run_once: true

# ── host lookup ───────────────────────────────────────────────────────────────

- name: Show variables for a specific host
  display_inventory:
    host: webserver01
  delegate_to: localhost
  run_once: true

# ── Verbosity gating ──────────────────────────────────────────────────────────

# ── export mode ───────────────────────────────────────────────────────────────

- name: Export raw (non-inherited) vars to YAML file
  display_inventory:
    mode: list
    show_hostvars: true
    export: true
    output_format: yaml
    export_file: /tmp/inventory_export.yml
  delegate_to: localhost
  run_once: true

# ── Role usage ────────────────────────────────────────────────────────────────

'''

RETURN = r'''
output:
  description: Rendered inventory text (JSON / YAML / TOML / graph).
  returned: success and not skipped
  type: str
inventory_data:
  description: Native dict representation (when mode=list or host is set).
  returned: when mode=list or host is set, and not skipped
  type: dict
sources_used:
  description: Inventory source paths that were loaded.
  returned: success and not skipped
  type: list
export_file:
  description: Path written when export_file was specified.
  returned: when export_file is provided and not skipped
  type: str
'''

from ansible.module_utils.basic import AnsibleModule


def main():
    # Stub only — the action plugin (action_plugins/display_inventory.py)
    # intercepts every task invocation before this code runs.
    module = AnsibleModule(
        argument_spec=dict(
            mode=dict(type="str", choices=["list", "graph"]),
            host=dict(type="str"),
            show_vars=dict(type="bool", default=False),
            show_hostvars=dict(type="bool", default=False),
            export=dict(type="bool", default=False),
            export_file=dict(type="path"),
            group=dict(type="str"),
            pattern=dict(type="str"),
            output_format=dict(type="str", default="json",
                               choices=["json", "yaml", "toml"]),
            inventory=dict(type="str"),
        ),
        mutually_exclusive=[["mode", "host"]],
        required_one_of=[["mode", "host"]],
        supports_check_mode=True,
    )
    module.exit_json(
        changed=False,
        msg="Action plugin did not intercept this task. "
            "Ensure action_plugins/display_inventory.py is in place.",
    )


if __name__ == "__main__":
    main()
