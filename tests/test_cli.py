"""Tests for network_analyzer.cli module."""

import json
import sys
import unittest
from io import StringIO
from unittest.mock import patch

from network_analyzer.cli import build_parser, _parse_ports, cmd_json


class TestParsePortsHelper(unittest.TestCase):
    def test_single_port(self):
        self.assertEqual(_parse_ports("80"), [80])

    def test_multiple_ports(self):
        self.assertEqual(_parse_ports("22,80,443"), [22, 80, 443])

    def test_range(self):
        self.assertEqual(_parse_ports("8000-8003"), [8000, 8001, 8002, 8003])

    def test_mixed(self):
        self.assertEqual(_parse_ports("22,80-82,443"), [22, 80, 81, 82, 443])


class TestCliParser(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_ping_defaults(self):
        args = self.parser.parse_args(["ping", "8.8.8.8"])
        self.assertEqual(args.host, "8.8.8.8")
        self.assertEqual(args.count, 4)
        self.assertEqual(args.timeout, 2)

    def test_ping_custom_count(self):
        args = self.parser.parse_args(["ping", "8.8.8.8", "-c", "2"])
        self.assertEqual(args.count, 2)

    def test_scan_defaults(self):
        args = self.parser.parse_args(["scan", "127.0.0.1"])
        self.assertEqual(args.host, "127.0.0.1")
        self.assertIsNone(args.ports)
        self.assertFalse(args.show_closed)

    def test_scan_with_ports(self):
        args = self.parser.parse_args(["scan", "127.0.0.1", "-p", "22,80"])
        self.assertEqual(args.ports, "22,80")

    def test_dns_defaults(self):
        args = self.parser.parse_args(["dns", "example.com"])
        self.assertEqual(args.hostname, "example.com")
        self.assertIsNone(args.types)

    def test_dns_custom_types(self):
        args = self.parser.parse_args(["dns", "example.com", "-t", "A", "MX"])
        self.assertEqual(args.types, ["A", "MX"])

    def test_no_command_exits(self):
        with self.assertRaises(SystemExit):
            self.parser.parse_args([])


class TestCmdJson(unittest.TestCase):
    def test_outputs_valid_json(self):
        captured = StringIO()
        with patch("sys.stdout", captured):
            cmd_json(None)
        data = json.loads(captured.getvalue())
        self.assertIn("timestamp", data)
        self.assertIn("hostname", data)
        self.assertIn("interfaces", data)


if __name__ == "__main__":
    unittest.main()
