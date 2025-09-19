# vconfig
VCONFIG is going to be deprecated soon and I will miss it. So I created a new version which uses 'ip' undere the hood for those of us who are a bit Old Skool!

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
