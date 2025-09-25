#!/usr/bin/env python3
"""
vconfig.py — a vconfig-like wrapper implemented with ip(8).
Liam Romanis
https://github.com/liamromanis101/vconfig

Usage:

  add [interface-name] [vlan_id] [-name IFNAME]
  rem [vlan-name]
  set_flag [vlan-name] [flag-num] [0|1]
  set_flag [vlan-name] [0|1]
  set_egress_map [vlan-name] [skb_priority] [vlan_qos]
  set_ingress_map [vlan-name] [skb_priority] [vlan_qos]

Notes:
- Only creates/deletes VLAN links; it does not bring links up.
- set_flag supports: 1=reorder_hdr, 2=gvrp, 3=mvrp, 4=loose_binding.
- VLAN IDs are decimal (1..4094).
- On too-long/invalid interface names, the tool will prompt you for a shorter one.
"""

import os
import sys
import subprocess
import shlex
import re

# ---- ifname / retry helpers -------------------------------------------------

# Kernel IFNAMSIZ is 16 (including trailing NUL) → 15 visible chars
IFNAMSIZ = 16
MAX_IFNAME_LEN = IFNAMSIZ - 1

# iproute2 error text when the provided name is too long/invalid
_INVALID_IFNAME_RE = re.compile(r"(invalid ifname|not a valid ifname)", re.IGNORECASE)


def _valid_ifname(name):
    if not name or len(name) > MAX_IFNAME_LEN:
        return False
    if any(ch.isspace() for ch in name):
        return False
    if "/" in name:
        return False
    return True


def _prompt_for_ifname(suggest=None):
    """
    Ask the user for a valid interface name (≤15 chars, no whitespace or '/').
    Keeps prompting until a valid-looking name is entered.
    """
    while True:
        try:
            prompt = f"Interface name is too long/invalid. Enter a shorter name (≤{MAX_IFNAME_LEN} chars)"
            if suggest:
                prompt += f" [{suggest}]"
            prompt += ": "
            entered = input(prompt).strip()
        except EOFError:
            die("Aborted: no valid interface name provided.")
        name = entered or (suggest or "")
        if _valid_ifname(name):
            return name
        print(f"'{name}' is not a valid ifname. It must be ≤{MAX_IFNAME_LEN} chars, with no whitespace or '/'. Try again.")


def _replace_or_inject_name(cmd, new_name):
    """
    Replace token after 'name' if present; otherwise inject 'name <new_name>'
    before 'type vlan' if found, else append at end.
    """
    cmd2 = list(cmd)
    try:
        i = cmd2.index("name")
        if i + 1 < len(cmd2):
            cmd2[i + 1] = new_name
        else:
            cmd2.append(new_name)
        return cmd2
    except ValueError:
        pass

    try:
        j = cmd2.index("type")
        return cmd2[:j] + ["name", new_name] + cmd2[j:]
    except ValueError:
        return cmd2 + ["name", new_name]


def _extract_name_from_cmd(cmd):
    try:
        i = cmd.index("name")
        if i + 1 < len(cmd):
            return cmd[i + 1]
    except ValueError:
        pass
    return None


def run_ip_with_ifname_retry(cmd, vid=None):
    """
    Run ip(8) with recovery for 'invalid ifname' errors:
    - If ip returns an invalid/too-long ifname error, prompt the user
      for a shorter name (default suggestion: vlan<VID>) and retry.
    - If ip rejects the new name the same way, re-prompt.
    - For any other failure, abort with the real error (like run()).

    Returns: (CompletedProcess, final_interface_name)
    """
    current_cmd = list(cmd)

    while True:
        proc = subprocess.run(current_cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            final_name = _extract_name_from_cmd(current_cmd) or ""
            return proc, final_name

        combined = (proc.stderr or "") + (proc.stdout or "")
        if _INVALID_IFNAME_RE.search(combined):
            suggested = f"vlan{vid}" if vid is not None else None

            # Non-interactive: try one automatic fallback then bail
            if not sys.stdin.isatty():
                auto = suggested or "vlan0"
                if not _valid_ifname(auto):
                    auto = "vlan0"
                current_cmd = _replace_or_inject_name(current_cmd, auto)
                proc2 = subprocess.run(current_cmd, capture_output=True, text=True)
                if proc2.returncode == 0:
                    return proc2, auto
                die(proc.stderr.strip() or f"command failed: {' '.join(map(shlex.quote, current_cmd))}")

            # Interactive: keep prompting until accepted by ip(8)
            while True:
                new_name = _prompt_for_ifname(suggested)
                current_cmd = _replace_or_inject_name(current_cmd, new_name)
                proc2 = subprocess.run(current_cmd, capture_output=True, text=True)
                if proc2.returncode == 0:
                    return proc2, new_name
                combined2 = (proc2.stderr or "") + (proc2.stdout or "")
                if _INVALID_IFNAME_RE.search(combined2):
                    print(f"'{new_name}' was rejected by ip(8). Let's try another.")
                    continue
                die(proc2.stderr.strip() or f"command failed: {' '.join(map(shlex.quote, current_cmd))}")

        # Not an ifname error — behave like run()
        die(proc.stderr.strip() or f"command failed: {' '.join(map(shlex.quote, current_cmd))}")


# ---- stock helpers ----------------------------------------------------------

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


def parse_vlan_id(s):
    try:
        vid = int(s, 10)
    except ValueError:
        die(f"invalid vlan_id '{s}' (use decimal)")
    if not (1 <= vid <= 4094):
        die("vlan_id must be in range 1..4094")
    return vid


# ---- commands ---------------------------------------------------------------

def _extract_name_opt(args):
    """
    Extract -name/--name IFNAME from a free-form argv slice.
    Returns (ifname or None, remaining_args).
    """
    name = None
    rest = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-name", "--name"):
            if i + 1 >= len(args):
                die("'-name' requires a value")
            name = args[i + 1]
            i += 2
            continue
        rest.append(a)
        i += 1
    return name, rest


def cmd_add(args):
    # add [interface-name] [vlan_id] [-name IFNAME]
    name_opt, core = _extract_name_opt(args)
    if len(core) != 2:
        die("usage: add [interface-name] [vlan_id] [-name IFNAME]")

    parent, vid_s = core
    vid = parse_vlan_id(vid_s)
    ensure_8021q()

    # If -name supplied, validate first, else default to parent.VID
    if name_opt is not None:
        if not _valid_ifname(name_opt):
            print(f"Provided -name '{name_opt}' is invalid (must be ≤{MAX_IFNAME_LEN} chars, no whitespace or '/').")
            # Prompt for a better one, suggesting vlan<VID>
            name = _prompt_for_ifname(f"vlan{vid}")
        else:
            name = name_opt
    else:
        name = f"{parent}.{vid}"

    base_cmd = ["ip", "link", "add", "link", parent, "name", name, "type", "vlan", "id", str(vid)]
    run_ip_with_ifname_retry(base_cmd, vid=vid)
    # vconfig prints nothing on success
    return 0


def cmd_rem(args):
    if len(args) != 1:
        die("usage: rem [vlan-name]")
    dev = args[0]
    run(["ip", "link", "delete", dev])
    return 0


def _on_off(v):
    if v not in ("0", "1"):
        die("flag value must be 0 or 1")
    return "on" if v == "1" else "off"


def cmd_set_flag(args):
    # set_flag <dev> <0|1>
    # set_flag <dev> <flagnum> <0|1>
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
    die("usage: set_flag [vlan-name] [flag-num] [0|1] (or) set_flag [vlan-name] [0|1]")


def cmd_set_egress_map(args):
    # set_egress_map <dev> <skb> <qos>
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
    # set_ingress_map <dev> <skb> <qos>  (ip expects qos:skb)
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
        # set_name_type removed; use -name on 'add' instead
    }
    func = dispatch.get(cmd)
    if not func:
        usage()
    func(args)


if __name__ == "__main__":
    main()
