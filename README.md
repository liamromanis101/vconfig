# vconfig

`vconfig` is being deprecated, and I’ll miss it. This is a drop-in style wrapper that uses `ip(8)` under the hood for those of us who are a bit old-skool.

> **Note:** The command name in the examples is `vconfig`. If your installed console script is different (e.g. `vconfig-cli`), substitute that name.

---

## Usage

`vconfig.py` — a `vconfig`-compatible wrapper implemented with `ip(8)`.

**Commands** (same as `vconfig -h`):

```
add             [interface-name] [vlan_id] [-name ifname]
rem             [vlan-name]
set_flag        [vlan-name] [flag-num] [0|1]
set_flag        [vlan-name] [0|1]                 # compatibility: reorder_hdr only
set_egress_map  [vlan-name] [skb_priority] [vlan_qos]
set_ingress_map [vlan-name] [skb_priority] [vlan_qos]
```

**Notes**

- Only creates/deletes VLAN links; it does not bring links up (mirrors `vconfig` behavior).
- `set_flag` supports: `1=reorder_hdr`, `2=gvrp`, `3=mvrp`, `4=loose_binding`.
- VLAN IDs are normalized to decimal (avoid octal/hex pitfalls).

---

## Example usage

> This script must be run as root. If `pip` installed the script into `~/.local/bin`, `sudo` may not see it due to a restricted `PATH`. You can run it like this:

```bash
sudo env "PATH=$PATH" vconfig
```
> Or copy the script into root's ~/.local/bin, or install it as root..

**Create `eth0.10` using current name-type (default: `DEV_PLUS_VID_NO_PAD`)**

```bash
sudo vconfig add eth0 10
```

**Remove it**

```bash
sudo vconfig rem eth0.10
```

**Match vconfig’s reorder header flag**

```bash
sudo vconfig set_flag eth0.10 1 1     # enable reorder_hdr
# (or simply: sudo vconfig set_flag eth0.10 1)
```

**QoS maps (same args as vconfig)**

```bash
sudo vconfig set_egress_map  eth0.10 5 3    # skb prio 5 -> VLAN PCP 3
sudo vconfig set_ingress_map eth0.10 4 2    # VLAN PCP 2 -> skb prio 4
```

**Naming style (persists in `/run`)**

```bash
sudo vconfig set_name_type VLAN_PLUS_VID_NO_PAD  # next add => vlan5
```
