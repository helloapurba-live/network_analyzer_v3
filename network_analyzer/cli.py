"""Command-line interface for Network Analyzer v3."""

import argparse
import json
import sys

from network_analyzer.analyzer import (
    get_network_summary,
    ping_host,
    scan_ports,
    resolve_dns,
    get_port_name,
    validate_host,
    COMMON_PORTS,
)


def cmd_summary(_args):
    """Print a summary of all network interfaces and I/O counters."""
    summary = get_network_summary()
    print(f"Timestamp : {summary['timestamp']}")
    print(f"Hostname  : {summary['hostname']}")
    print()
    print("Network Interfaces:")
    print("-" * 60)
    for iface in summary["interfaces"]:
        status = "UP" if iface.get("is_up") else ("DOWN" if iface.get("is_up") is False else "?")
        speed = iface.get("speed_mbps")
        speed_str = f"  Speed: {speed} Mbps" if speed else ""
        mtu = iface.get("mtu")
        mtu_str = f"  MTU: {mtu}" if mtu else ""
        print(f"  {iface['name']} [{status}]{speed_str}{mtu_str}")
        for addr in iface["addresses"]:
            mask = f"/{addr['netmask']}" if addr.get("netmask") else ""
            print(f"    {addr['family']:12s} {addr['address']}{mask}")
    if "io_counters" in summary:
        print()
        print("I/O Counters:")
        print("-" * 60)
        for nic, c in summary["io_counters"].items():
            print(f"  {nic}:")
            print(f"    Sent: {c['bytes_sent']:,} bytes  Recv: {c['bytes_recv']:,} bytes")
            print(f"    Errors in/out: {c['errin']}/{c['errout']}  Drops in/out: {c['dropin']}/{c['dropout']}")


def cmd_ping(args):
    """Ping a host and display results."""
    if not validate_host(args.host):
        print(f"Error: '{args.host}' is not a valid host or IP address.", file=sys.stderr)
        sys.exit(1)

    print(f"Pinging {args.host} ({args.count} packets, timeout {args.timeout}s)...")
    result = ping_host(args.host, count=args.count, timeout=args.timeout)
    print(f"  Reachable     : {'Yes' if result['reachable'] else 'No'}")
    print(f"  Packets sent  : {result['packets_sent']}")
    print(f"  Packets recv  : {result['packets_received']}")
    print(f"  Packet loss   : {result['packet_loss_pct']}%")
    if result["avg_ms"] is not None:
        print(f"  RTT min/avg/max: {result['min_ms']}/{result['avg_ms']}/{result['max_ms']} ms")
    if not result["reachable"]:
        sys.exit(2)


def cmd_scan(args):
    """Scan TCP ports on a host."""
    if not validate_host(args.host):
        print(f"Error: '{args.host}' is not a valid host or IP address.", file=sys.stderr)
        sys.exit(1)

    if args.ports:
        ports = _parse_ports(args.ports)
    else:
        ports = sorted(COMMON_PORTS.keys())

    print(f"Scanning {len(ports)} port(s) on {args.host} (timeout {args.timeout}s)...")
    results = scan_ports(args.host, ports, timeout=args.timeout)
    open_ports = [p for p, open_ in sorted(results.items()) if open_]
    closed_ports = [p for p, open_ in sorted(results.items()) if not open_]

    print(f"\nOpen ports ({len(open_ports)}):")
    if open_ports:
        for port in open_ports:
            print(f"  {port:5d}  {get_port_name(port)}")
    else:
        print("  (none)")

    if args.show_closed:
        print(f"\nClosed/filtered ports ({len(closed_ports)}):")
        for port in closed_ports:
            print(f"  {port:5d}  {get_port_name(port)}")


def cmd_dns(args):
    """Resolve DNS records for a hostname."""
    record_types = [r.upper() for r in args.types] if args.types else None
    print(f"DNS lookup for: {args.hostname}")
    print("-" * 60)
    records = resolve_dns(args.hostname, record_types=record_types)
    for rtype, values in records.items():
        if values:
            print(f"  {rtype:8s}: {', '.join(values)}")
        else:
            print(f"  {rtype:8s}: (no records)")


def cmd_json(args):
    """Output the full network summary as JSON."""
    summary = get_network_summary()
    print(json.dumps(summary, indent=2))


def _parse_ports(ports_str):
    """Parse a comma/range port specification like '22,80,443,8000-8100'."""
    ports = set()
    for part in ports_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            ports.update(range(int(start), int(end) + 1))
        else:
            ports.add(int(part))
    return sorted(ports)


def build_parser():
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="network-analyzer",
        description="Network Analyzer v3 — analyze network interfaces, connectivity, and services.",
    )
    parser.add_argument("--version", action="version", version="network-analyzer 3.0.0")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # summary
    p_summary = sub.add_parser("summary", help="Show network interfaces and I/O counters")
    p_summary.set_defaults(func=cmd_summary)

    # ping
    p_ping = sub.add_parser("ping", help="Ping a host")
    p_ping.add_argument("host", help="Hostname or IP address")
    p_ping.add_argument("-c", "--count", type=int, default=4, help="Number of packets (default: 4)")
    p_ping.add_argument("-t", "--timeout", type=int, default=2, help="Timeout per packet in seconds (default: 2)")
    p_ping.set_defaults(func=cmd_ping)

    # scan
    p_scan = sub.add_parser("scan", help="Scan TCP ports on a host")
    p_scan.add_argument("host", help="Hostname or IP address")
    p_scan.add_argument("-p", "--ports", help="Ports to scan: e.g. '22,80,443' or '8000-8100' (default: common ports)")
    p_scan.add_argument("-t", "--timeout", type=float, default=1.0, help="Connection timeout in seconds (default: 1)")
    p_scan.add_argument("--show-closed", action="store_true", help="Also show closed/filtered ports")
    p_scan.set_defaults(func=cmd_scan)

    # dns
    p_dns = sub.add_parser("dns", help="Resolve DNS records for a hostname")
    p_dns.add_argument("hostname", help="Hostname to resolve")
    p_dns.add_argument("-t", "--types", nargs="+", help="Record types (default: A AAAA MX NS TXT)")
    p_dns.set_defaults(func=cmd_dns)

    # json
    p_json = sub.add_parser("json", help="Output full network summary as JSON")
    p_json.set_defaults(func=cmd_json)

    return parser


def main():
    """Entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
