# vconfig
VCONFIG is going to be deprecated soon and I will miss it. So I created a new version which uses 'ip' undere the hood for those of us who are a bit Old Skool!

# Usage
text"""
vconfig.py — a vconfig-compatible wrapper implemented with ip(8).

Usage (same as vconfig -h):
  add             [interface-name] [vlan_id]
  rem             [vlan-name]
  set_flag        [vlan-name] [flag-num] [0|1]
  set_flag        [vlan-name] [0|1]                 # compatibility: reorder_hdr only
  set_egress_map  [vlan-name] [skb_priority] [vlan_qos]
  set_ingress_map [vlan-name] [skb_priority] [vlan_qos]
  set_name_type   [name-type]

name-type one of:
  VLAN_PLUS_VID (vlan0005), VLAN_PLUS_VID_NO_PAD (vlan5),
  DEV_PLUS_VID (eth0.0005), DEV_PLUS_VID_NO_PAD (eth0.5)

Notes:
- Only creates/deletes VLAN links; it does not bring links up (mirrors vconfig).
- set_flag supports: 1=reorder_hdr, 2=gvrp, 3=mvrp, 4=loose_binding.
- VLAN IDs are normalized to decimal (avoid octal/hex pitfalls).
"""

# Example Usage

## Create eth0.10 using current name-type (default: DEV_PLUS_VID_NO_PAD)
sudo vconfig add eth0 10

## Remove it
sudo vconfig rem eth0.10

## Match vconfig’s reorder header flag:
sudo vconfig set_flag eth0.10 1 1     # enable reorder_hdr (or: sudo vconfig set_flag eth0.10 1)

## QoS maps (same args as vconfig):
sudo vconfig set_egress_map  eth0.10 5 3    # skb prio 5 -> VLAN PCP 3
sudo vconfig set_ingress_map eth0.10 4 2    # VLAN PCP 2 -> skb prio 4

## Naming style (persists in /run):
sudo vconfig set_name_type VLAN_PLUS_VID_NO_PAD  # next add => vlan5
