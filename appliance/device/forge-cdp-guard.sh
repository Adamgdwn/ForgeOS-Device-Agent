#!/system/bin/sh
# Source from the root session guard. Keep Chromium's loopback control endpoint
# available only to the service UID and root, for exactly the session lifetime.
forge_cdp_chain=
forge_cdp_v4=
forge_cdp_v6=

forge_cdp_stop() {
    for family in 4 6; do
        if [ "$family" = 4 ]; then
            tool=iptables address=127.0.0.1 flag="$forge_cdp_v4"
        else
            tool=ip6tables address=::1 flag="$forge_cdp_v6"
        fi
        [ -n "$flag" ] || continue
        "$tool" -w 2 -D OUTPUT -p tcp -d "$address" --dport 9224 -j "$forge_cdp_chain" 2>/dev/null || true
        "$tool" -w 2 -F "$forge_cdp_chain" 2>/dev/null || true
        "$tool" -w 2 -X "$forge_cdp_chain" 2>/dev/null || true
    done
    forge_cdp_chain= forge_cdp_v4= forge_cdp_v6=
}

forge_cdp_start() {
    [ -z "$forge_cdp_chain" ] || return 1
    forge_cdp_chain="FORGE_CDP_$$"
    for family in 4 6; do
        if [ "$family" = 4 ]; then tool=iptables address=127.0.0.1
        else tool=ip6tables address=::1; fi
        if ! "$tool" -w 2 -N "$forge_cdp_chain"; then
            forge_cdp_stop
            return 1
        fi
        if [ "$family" = 4 ]; then forge_cdp_v4=1; else forge_cdp_v6=1; fi
        if ! "$tool" -w 2 -A "$forge_cdp_chain" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN ||
           ! "$tool" -w 2 -A "$forge_cdp_chain" -m owner --uid-owner 0 -j RETURN ||
           ! "$tool" -w 2 -A "$forge_cdp_chain" -m owner --uid-owner 65000 -j RETURN ||
           ! "$tool" -w 2 -A "$forge_cdp_chain" -j REJECT ||
           ! "$tool" -w 2 -I OUTPUT 1 -p tcp -d "$address" --dport 9224 -j "$forge_cdp_chain"; then
            forge_cdp_stop
            return 1
        fi
    done
}
