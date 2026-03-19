# display_inventory v3.3.1 — Ansible Action Plugin + Module

Displays Ansible inventory in multiple formats, mirroring `ansible-inventory`.
All inventory work is done **on the controller** via Ansible's own Python API —
no subprocess is spawned and no extra packages are installed on remote hosts.

---

## Requirements

### Controller (where ansible-playbook runs)

| Requirement | Version | Notes |
|---|---|---|
| Python | ≥ 3.8 | Standard on any supported Ansible controller |
| ansible-core | ≥ 2.9 | Provides `InventoryManager`, `VariableManager`, `DataLoader` |
| PyYAML | any | Bundled with ansible-core; required for `output_format: yaml` |
| `tomli_w` **or** `toml` | any | Optional; required only for `output_format: toml` — install with `pip install tomli_w` |

### Managed hosts

None. The plugin runs entirely on the controller. No Python packages, no SSH
file transfers, and no remote execution take place.

---

## Directory layout

```
.
├── ansible.cfg
├── display_inventory_demo.yml
├── action_plugins/
│   └── display_inventory.py      ← controller-side plugin (does all the work)
├── library/
│   └── display_inventory.py      ← stub module (docs + argument spec only)
└── roles/
    └── display_inventory/
        ├── defaults/main.yml
        ├── meta/main.yml
        └── tasks/main.yml
```

## Why two files?

Ansible modules run on the **target host**. Only `ansible.module_utils.*` is
transferred there — the full `ansible` package is not available. Classes like
`InventoryManager`, `VariableManager`, and `DataLoader` only exist on the
controller. The solution is an **action plugin**:

| File | Where it runs | What it does |
|---|---|---|
| `action_plugins/display_inventory.py` | **Controller** | Loads inventory via Python API, renders output |
| `library/display_inventory.py` | Never executed remotely | Provides `ansible-doc` docs and argument spec |

When Ansible sees a task named `display_inventory`, it checks for a matching
action plugin first. The action plugin intercepts the task, does everything on
the controller, and returns the result directly — the stub module is never
transferred to a host.

---

## Parameters

### Mode (required — choose one)

| Parameter | Type | Description |
|---|---|---|
| `mode` | str | `list` — structured host/group output. `graph` — hierarchy tree. Mutually exclusive with `host`. |
| `host` | str | Show all variables for this specific host. Mutually exclusive with `mode`. |

### Output control

| Parameter | Type | Default | Description |
|---|---|---|---|
| `show_vars` | bool | `false` | Include group-level variables in `list` output; include group and host variables inline in `graph` output. |
| `show_hostvars` | bool | `false` | Populate `_meta.hostvars` with each host's full merged variable set. Only meaningful with `mode: list`. Disabled by default because resolving every host's vars can be slow on large inventories. |
| `export` | bool | `false` | Use only variables explicitly set on each host or group object — no inheritance from parent groups. Mirrors `ansible-inventory --export`. Only meaningful with `mode: list` or `show_hostvars: true`. |
| `output_format` | str | `json` | Serialisation format for `list` and `host` output. Choices: `json`, `yaml`, `toml`. Graph output is always plain text regardless of this setting. See **Export formats** below. |

### Scope

| Parameter | Type | Default | Description |
|---|---|---|---|
| `group` | str | — | Limit output to hosts that belong to this group. In `graph` mode this group becomes the root of the tree. |
| `pattern` | str | — | Further filter displayed hosts to those whose names match this shell-style wildcard (`fnmatch`). Supports `*`, `?`, and `[seq]`. Example: `web*` matches `web1`, `webserver`, etc. |

### File export

| Parameter | Type | Default | Description |
|---|---|---|---|
| `export_file` | path | — | Base path for the output file. The plugin automatically appends a `YYYYMMDD_HHMM` timestamp and the correct extension for the chosen `output_format` (`.json`, `.yml`, or `.toml`). Example: `export_file: /tmp/inventory` with `output_format: yaml` produces `/tmp/inventory_20260318_1430.yml`. |

### Inventory source

| Parameter | Type | Default | Description |
|---|---|---|---|
| `inventory` | str | — | Override the inventory source (file path or comma-separated host list). When omitted the plugin reuses the sources already loaded by the current play. |

---

## Export formats

### `json` (default)

Standard JSON, pretty-printed with 4-space indentation and sorted keys.
Compatible with any tool that consumes the `ansible-inventory --list` JSON
schema, including AWX / Ansible Automation Platform dynamic inventory sources.

```json
{
    "_meta": {
        "hostvars": {
            "web1": {"ansible_host": "10.0.0.1"}
        }
    },
    "all": {"children": ["webservers", "ungrouped"]},
    "webservers": {"hosts": ["web1"]}
}
```

File extension: `.json`

### `yaml`

Human-readable YAML. Useful for diffing snapshots in version control or reading
output at a glance. Requires PyYAML, which is bundled with ansible-core.

```yaml
_meta:
  hostvars:
    web1:
      ansible_host: 10.0.0.1
all:
  children:
  - webservers
  - ungrouped
webservers:
  hosts:
  - web1
```

File extension: `.yml`

### `toml`

TOML format. Requires the `tomli_w` package (preferred) or the legacy `toml`
package on the controller. Install with:

```bash
pip install tomli_w
```

File extension: `.toml`

> **Note:** TOML does not support mixed-type arrays or `null` values. If your
> inventory variables contain these, use `json` or `yaml` instead.

---

## Return values

| Key | Type | Returned | Description |
|---|---|---|---|
| `output` | str | always (not skipped) | Rendered inventory text in the chosen format |
| `inventory_data` | dict | when `mode: list` or `host` is set | Native Python dict — useful for inspecting data in subsequent tasks |
| `sources_used` | list | always (not skipped) | Inventory source paths that were loaded |
| `export_file` | str | when `export_file` is set | Full timestamped path of the file that was written |

---

## Quick-start

```yaml
- name: Show inventory graph
  display_inventory:
    mode: graph
  delegate_to: localhost
  run_once: true
```

```yaml
- name: Snapshot inventory to a timestamped YAML file
  display_inventory:
    mode: list
    show_hostvars: true
    output_format: yaml
    export_file: /tmp/inventory_snapshot
  delegate_to: localhost
  run_once: true
# Produces e.g. /tmp/inventory_snapshot_20260318_1430.yml
```

```yaml
- name: Show just the webservers group
  display_inventory:
    mode: graph
    group: webservers
  delegate_to: localhost
  run_once: true
```

---

## Role usage

```yaml
- name: Display inventory via role
  hosts: all
  gather_facts: false
  roles:
    - role: display_inventory
      vars:
        display_inventory_mode: graph
        display_inventory_show_vars: true
        display_inventory_group: webservers
```

Override any variable from `roles/display_inventory/defaults/main.yml` inline
or in `group_vars` / `host_vars`.

---

## Installation

1. Copy `action_plugins/display_inventory.py` and `library/display_inventory.py`
   into your project (paths are configured in `ansible.cfg`).
2. Optionally copy `roles/display_inventory/` for the pre-built role wrapper.
3. Install `tomli_w` on the controller only if you need `output_format: toml`.

---

## Changelog

| Version | Notes |
|---|---|
| 3.3.1 | Added export format documentation and requirements section to README |
| 3.3.0 | Fixed group-scoped graph rendering; removed `inventory.subset()` misuse |
| 3.2.x | Timestamped export filenames; format-correct file extensions |
| 3.1.x | Consolidated `list`/`graph` into `mode`; added `show_vars`, `show_hostvars`, `group`, `pattern`, `output_format`, `export_file` |
| 1.0.0 | Initial release |

---

## License

GNU General Public License v3.0 or later.
