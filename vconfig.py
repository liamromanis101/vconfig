#!/usr/bin/env python3
"""
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
import os, sys, subprocess, shlex, errno, json

STATE_FILE = "/run/vconfig_name_type"
DEFAULT_NAME_TYPE = "DEV_PLUS_VID_NO_PAD"
ALLOWED_NAME_TYPES = {
    "VLAN_PLUS_VID",
    "VLAN_PLUS_VID_NO_PAD",
    "DEV_PLUS_VID",
    "DEV_PLUS_VID_NO_PAD",
}

def die(msg, code=1):
    print(f"vconfig: {msg}", file=sys.stderr)
    sys.exit(code)

def run(cmd):
    try:
        subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        die(e.stderr.strip() or f"command failed: {' '.join(map(shlex.quote, cmd))}")

def ensure_root():
    if os.geteuid() != 0:
        die("must be run as root")

def ensure_8021q():
    if not os.path.isdir("/sys/module/8021q"):
        run(["modprobe", "8021q"])

def read_name_type():
    try:
        with open(STATE_FILE, "r") as f:
            t = f.read().strip()
            if t in ALLOWED_NAME_TYPES:
                return t
    except FileNotFoundError:
        pass
    return DEFAULT_NAME_TYPE

def write_name_type(t):
    if t not in ALLOWED_NAME_TYPES:
        die(f"unknown name-type '{t}'")
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        f.write(t)

def parse_vlan_id(s):
    # vconfig historically expects decimal; normalize to decimal to avoid ip(8) octal/hex surprises
    try:
        vid = int(s, 10)
    except ValueError:
        die(f"invalid vlan_id '{s}' (use decimal)")
    if not (0 <= vid <= 4094):
        die("vlan_id must be in range 0..4094")
    return vid

def vlan_name(parent, vid, name_type):
    if name_type == "VLAN_PLUS_VID":
        return f"vlan{vid:04d}"
    if name_type == "VLAN_PLUS_VID_NO_PAD":
        return f"vlan{vid}"
    if name_type == "DEV_PLUS_VID":
        return f"{parent}.{vid:04d}"
    if name_type == "DEV_PLUS_VID_NO_PAD":
        return f"{parent}.{vid}"
    return f"{parent}.{vid}"

def cmd_add(args):
    if len(args) != 2:
        die("usage: add [interface-name] [vlan_id]")
    parent, vid_s = args
    vid = parse_vlan_id(vid_s)
    ensure_8021q()
    name = vlan_name(parent, vid, read_name_type())
    run(["ip", "link", "add", "link", parent, "name", name, "type", "vlan", "id", str(vid)])
    # Match vconfig: no extra output on success.
    return 0

def cmd_rem(args):
    if len(args) != 1:
        die("usage: rem [vlan-name]")
    dev = args[0]
    run(["ip", "link", "delete", dev])
    return 0

def cmd_set_name_type(args):
    if len(args) != 1:
        die("usage: set_name_type [name-type]")
    write_name_type(args[0])
    return 0

def _on_off(v):
    if v not in ("0", "1"):
        die("flag value must be 0 or 1")
    return "on" if v == "1" else "off"

def cmd_set_flag(args):
    # vconfig had two forms:
    #   set_flag <vlan-dev> <flag-num> <0|1>
    #   set_flag <vlan-dev> <0|1>   (reorder_hdr only)
    if len(args) == 2:
        dev, val = args
        run(["ip", "link", "set", "dev", dev, "type", "vlan", "reorder_hdr", _on_off(val)])
        return 0
    if len(args) == 3:
        dev, flagnum, val = args
        mapping = {
            "1": "reorder_hdr",
            "2": "gvrp",
            "3": "mvrp",
            "4": "loose_binding",
        }
        flag = mapping.get(flagnum)
        if not flag:
            die("flag-num must be one of 1(reorder_hdr), 2(gvrp), 3(mvrp), 4(loose_binding)")
        run(["ip", "link", "set", "dev", dev, "type", "vlan", flag, _on_off(val)])
        return 0
    die("usage: set_flag [vlan-name] [flag-num] [0|1]  (or)  set_flag [vlan-name] [0|1]")

def cmd_set_egress_map(args):
    # vconfig:  set_egress_map <vlan-dev> <skb_priority> <vlan_qos>
    if len(args) != 3:
        die("usage: set_egress_map [vlan-name] [skb_priority] [vlan_qos]")
    dev, skb, qos = args
    try:
        int(skb); int(qos)
    except ValueError:
        die("skb_priority and vlan_qos must be integers")
    run(["ip", "link", "set", "dev", dev, "type", "vlan", "egress-qos-map", f"{skb}:{qos}"])
    return 0

def cmd_set_ingress_map(args):
    # vconfig:  set_ingress_map <vlan-dev> <skb_priority> <vlan_qos>
    # ip(8) expects qos:skb for ingress
    if len(args) != 3:
        die("usage: set_ingress_map [vlan-name] [skb_priority] [vlan_qos]")
    dev, skb, qos = args
    try:
        int(skb); int(qos)
    except ValueError:
        die("skb_priority and vlan_qos must be integers")
    run(["ip", "link", "set", "dev", dev, "type", "vlan", "ingress-qos-map", f"{qos}:{skb}"])
    return 0

def usage():
    print(__doc__.strip())
    sys.exit(2)

def main():
    ensure_root()
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        usage()
    cmd, *args = sys.argv[1:]
    dispatch = {
        "add": cmd_add,
        "rem": cmd_rem,
        "set_flag": cmd_set_flag,
        "set_egress_map": cmd_set_egress_map,
        "set_ingress_map": cmd_set_ingress_map,
        "set_name_type": cmd_set_name_type,
    }
    func = dispatch.get(cmd)
    if not func:
        usage()
    func(args)

if __name__ == "__main__":
    main()
