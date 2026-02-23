"""Tests for network_analyzer.analyzer module."""

import ipaddress
import socket
import unittest
from unittest.mock import MagicMock, patch

from network_analyzer.analyzer import (
    get_port_name,
    ping_host,
    resolve_dns,
    scan_ports,
    validate_host,
    validate_ip,
    _parse_ping_output,
    COMMON_PORTS,
)


class TestValidateIp(unittest.TestCase):
    def test_valid_ipv4(self):
        self.assertTrue(validate_ip("192.168.1.1"))

    def test_valid_ipv6(self):
        self.assertTrue(validate_ip("::1"))

    def test_invalid_ip(self):
        self.assertFalse(validate_ip("not_an_ip"))

    def test_invalid_string(self):
        self.assertFalse(validate_ip("256.0.0.1"))


class TestValidateHost(unittest.TestCase):
    def test_valid_ip(self):
        self.assertTrue(validate_host("127.0.0.1"))

    def test_valid_ipv6_loopback(self):
        self.assertTrue(validate_host("::1"))

    def test_invalid_host(self):
        with patch("network_analyzer.analyzer.socket.gethostbyname",
                   side_effect=socket.gaierror):
            self.assertFalse(validate_host("this.host.does.not.exist.invalid"))


class TestGetPortName(unittest.TestCase):
    def test_known_ports(self):
        self.assertEqual(get_port_name(80), "HTTP")
        self.assertEqual(get_port_name(443), "HTTPS")
        self.assertEqual(get_port_name(22), "SSH")
        self.assertEqual(get_port_name(53), "DNS")

    def test_unknown_port(self):
        self.assertEqual(get_port_name(9999), "Unknown")

    def test_all_common_ports_have_names(self):
        for port in COMMON_PORTS:
            self.assertNotEqual(get_port_name(port), "Unknown")


class TestParsePingOutput(unittest.TestCase):
    LINUX_OUTPUT = (
        "PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.\n"
        "64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 time=12.3 ms\n"
        "\n"
        "--- 8.8.8.8 ping statistics ---\n"
        "4 packets transmitted, 4 received, 0% packet loss, time 3004ms\n"
        "rtt min/avg/max/mdev = 11.5/12.3/13.1/0.5 ms\n"
    )

    def test_parse_linux_packets(self):
        result = {
            "host": "8.8.8.8",
            "packets_sent": 4,
            "packets_received": 0,
            "packet_loss_pct": 100.0,
            "min_ms": None,
            "avg_ms": None,
            "max_ms": None,
            "reachable": False,
        }
        _parse_ping_output(self.LINUX_OUTPUT, result, "linux")
        self.assertEqual(result["packets_received"], 4)
        self.assertEqual(result["packet_loss_pct"], 0.0)
        self.assertAlmostEqual(result["min_ms"], 11.5)
        self.assertAlmostEqual(result["avg_ms"], 12.3)
        self.assertAlmostEqual(result["max_ms"], 13.1)


class TestScanPorts(unittest.TestCase):
    def test_open_port(self):
        """A port that accepts connections should be reported as open."""
        import threading
        import time

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        def _serve():
            try:
                conn, _ = server.accept()
                conn.close()
            except OSError:
                pass
            finally:
                server.close()

        t = threading.Thread(target=_serve, daemon=True)
        t.start()
        time.sleep(0.05)

        results = scan_ports("127.0.0.1", [port], timeout=2)
        self.assertTrue(results[port])
        t.join(timeout=2)

    def test_closed_port(self):
        """A port with nothing listening should be reported as closed."""
        # Find a port that is almost certainly free
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
        s.close()

        results = scan_ports("127.0.0.1", [free_port], timeout=1)
        self.assertFalse(results[free_port])

    def test_invalid_host(self):
        results = scan_ports("this.host.does.not.exist.invalid", [80], timeout=1)
        self.assertFalse(results[80])


class TestResolveDns(unittest.TestCase):
    def test_loopback_a_record(self):
        """Resolving localhost should return 127.0.0.1 (A record)."""
        records = resolve_dns("localhost", record_types=["A"])
        self.assertIn("A", records)
        self.assertTrue(len(records["A"]) >= 1)

    def test_nxdomain_returns_empty(self):
        """An NXDOMAIN hostname should return empty record lists."""
        records = resolve_dns(
            "this.host.does.not.exist.invalid",
            record_types=["A"],
        )
        self.assertIn("A", records)
        self.assertEqual(records["A"], [])


class TestPingHost(unittest.TestCase):
    def test_unreachable_host_structure(self):
        """Result dict should have the expected keys even for an unreachable host."""
        with patch("network_analyzer.analyzer.subprocess.run",
                   side_effect=FileNotFoundError):
            result = ping_host("192.0.2.1", count=1, timeout=1)
        self.assertIn("reachable", result)
        self.assertIn("packets_sent", result)
        self.assertIn("packets_received", result)
        self.assertIn("packet_loss_pct", result)
        self.assertFalse(result["reachable"])

    def test_loopback_reachable(self):
        """Pinging loopback should succeed on most systems."""
        result = ping_host("127.0.0.1", count=1, timeout=2)
        self.assertIn("reachable", result)
        # Don't hard-assert True because some CI environments block ping


if __name__ == "__main__":
    unittest.main()
