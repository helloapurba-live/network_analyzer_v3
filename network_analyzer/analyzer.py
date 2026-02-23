"""Core network analysis functionality."""

import socket
import subprocess
import platform
import ipaddress
from datetime import datetime, timezone

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import dns.resolver
    HAS_DNSPYTHON = True
except ImportError:
    HAS_DNSPYTHON = False


def get_network_interfaces():
    """Return information about all network interfaces.

    Returns:
        list[dict]: A list of interface info dicts with keys:
            name, addresses, is_up, stats (if psutil available).
    """
    interfaces = []

    if HAS_PSUTIL:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for name, addr_list in addrs.items():
            addresses = []
            for addr in addr_list:
                entry = {
                    "family": addr.family.name,
                    "address": addr.address,
                    "netmask": addr.netmask,
                    "broadcast": addr.broadcast,
                }
                addresses.append(entry)
            iface = {
                "name": name,
                "addresses": addresses,
                "is_up": stats[name].isup if name in stats else None,
            }
            if name in stats:
                iface["speed_mbps"] = stats[name].speed
                iface["mtu"] = stats[name].mtu
            interfaces.append(iface)
    else:
        # Fallback: use socket to get hostname/IP
        hostname = socket.gethostname()
        try:
            ip = socket.gethostbyname(hostname)
        except socket.gaierror:
            ip = "127.0.0.1"
        interfaces.append({
            "name": "default",
            "addresses": [{"family": "AF_INET", "address": ip,
                           "netmask": None, "broadcast": None}],
            "is_up": None,
        })

    return interfaces


def ping_host(host, count=4, timeout=2):
    """Ping a host and return latency statistics.

    Args:
        host (str): Hostname or IP address to ping.
        count (int): Number of ping packets to send.
        timeout (int): Timeout in seconds per packet.

    Returns:
        dict: keys - host, packets_sent, packets_received, packet_loss_pct,
              min_ms, avg_ms, max_ms, reachable.
    """
    result = {
        "host": host,
        "packets_sent": count,
        "packets_received": 0,
        "packet_loss_pct": 100.0,
        "min_ms": None,
        "avg_ms": None,
        "max_ms": None,
        "reachable": False,
    }

    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", str(count), "-w", str(timeout * 1000), host]
    else:
        cmd = ["ping", "-c", str(count), "-W", str(timeout), host]

    try:
        output = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout * count + 5,
        )
        if output.returncode == 0:
            result["reachable"] = True
            _parse_ping_output(output.stdout, result, system)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return result


def _parse_ping_output(output, result, system):
    """Parse ping command output to extract statistics."""
    lines = output.splitlines()
    for line in lines:
        line_lower = line.lower()
        # Packets received
        if "received" in line_lower or "packets received" in line_lower:
            parts = line.split(",")
            for part in parts:
                part = part.strip()
                if "received" in part.lower():
                    tokens = part.split()
                    for token in tokens:
                        try:
                            result["packets_received"] = int(token)
                            total = result["packets_sent"]
                            if total > 0:
                                lost = total - result["packets_received"]
                                result["packet_loss_pct"] = round(
                                    (lost / total) * 100, 1
                                )
                            break
                        except ValueError:
                            continue
        # RTT statistics (Linux/macOS: rtt min/avg/max/mdev)
        if "rtt" in line_lower or "round-trip" in line_lower:
            parts = line.split("=")
            if len(parts) == 2:
                stats_str = parts[1].strip().split("/")
                try:
                    result["min_ms"] = float(stats_str[0])
                    result["avg_ms"] = float(stats_str[1])
                    result["max_ms"] = float(stats_str[2].split()[0])
                except (IndexError, ValueError):
                    pass


def scan_ports(host, ports, timeout=1):
    """Scan a list of TCP ports on a host.

    Args:
        host (str): Hostname or IP address.
        ports (list[int]): Port numbers to scan.
        timeout (float): Connection timeout in seconds.

    Returns:
        dict: Mapping of port -> bool (True = open, False = closed/filtered).
    """
    results = {}
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        return {port: False for port in ports}

    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            code = sock.connect_ex((ip, port))
            results[port] = code == 0
        except (socket.error, OverflowError):
            results[port] = False
        finally:
            sock.close()

    return results


def resolve_dns(hostname, record_types=None):
    """Resolve DNS records for a hostname.

    Args:
        hostname (str): The hostname to resolve.
        record_types (list[str]): DNS record types to query (e.g. ['A', 'MX']).
            Defaults to ['A', 'AAAA', 'MX', 'NS', 'TXT'].

    Returns:
        dict: Mapping of record_type -> list of record values.
    """
    if record_types is None:
        record_types = ["A", "AAAA", "MX", "NS", "TXT"]

    records = {}

    if HAS_DNSPYTHON:
        resolver = dns.resolver.Resolver()
        for rtype in record_types:
            try:
                answers = resolver.resolve(hostname, rtype)
                records[rtype] = [str(r) for r in answers]
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN,
                    dns.resolver.Timeout, dns.exception.DNSException):
                records[rtype] = []
    else:
        # Fallback: only A records via socket
        try:
            info = socket.getaddrinfo(hostname, None, socket.AF_INET)
            records["A"] = list({r[4][0] for r in info})
        except socket.gaierror:
            records["A"] = []
        try:
            info6 = socket.getaddrinfo(hostname, None, socket.AF_INET6)
            records["AAAA"] = list({r[4][0] for r in info6})
        except socket.gaierror:
            records["AAAA"] = []

    return records


def get_network_summary():
    """Return a summary of the current network state.

    Returns:
        dict: timestamp, hostname, interfaces, io_counters (if psutil available).
    """
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "hostname": socket.gethostname(),
        "interfaces": get_network_interfaces(),
    }

    if HAS_PSUTIL:
        counters = psutil.net_io_counters(pernic=True)
        summary["io_counters"] = {
            nic: {
                "bytes_sent": c.bytes_sent,
                "bytes_recv": c.bytes_recv,
                "packets_sent": c.packets_sent,
                "packets_recv": c.packets_recv,
                "errin": c.errin,
                "errout": c.errout,
                "dropin": c.dropin,
                "dropout": c.dropout,
            }
            for nic, c in counters.items()
        }

    return summary


# Well-known port name mapping
COMMON_PORTS = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    143: "IMAP",
    443: "HTTPS",
    3306: "MySQL",
    5432: "PostgreSQL",
    6379: "Redis",
    8080: "HTTP-Alt",
    8443: "HTTPS-Alt",
    27017: "MongoDB",
}


def get_port_name(port):
    """Return the common service name for a port number, or 'Unknown'."""
    return COMMON_PORTS.get(port, "Unknown")


def validate_ip(address):
    """Return True if address is a valid IPv4 or IPv6 address."""
    try:
        ipaddress.ip_address(address)
        return True
    except ValueError:
        return False


def validate_host(host):
    """Return True if host is a valid hostname or IP address."""
    if validate_ip(host):
        return True
    try:
        socket.gethostbyname(host)
        return True
    except socket.gaierror:
        return False
