# network_analyzer_v3

A Python command-line tool for analyzing network interfaces, connectivity, and services.

## Installation

```bash
pip install -r requirements.txt
pip install -e .
```

## Usage

```
network-analyzer <command> [options]
```

### Commands

| Command | Description |
|---------|-------------|
| `summary` | Show all network interfaces and I/O counters |
| `ping <host>` | Ping a host and display latency statistics |
| `scan <host>` | Scan TCP ports on a host |
| `dns <hostname>` | Resolve DNS records for a hostname |
| `json` | Output full network summary as JSON |

### Examples

```bash
# Show network interface summary
network-analyzer summary

# Ping a host (4 packets)
network-analyzer ping 8.8.8.8

# Ping with custom count and timeout
network-analyzer ping google.com -c 10 -t 3

# Scan common ports on a host
network-analyzer scan 192.168.1.1

# Scan specific ports
network-analyzer scan 192.168.1.1 -p 22,80,443,8000-8100

# DNS lookup
network-analyzer dns example.com

# DNS lookup for specific record types
network-analyzer dns example.com -t A MX

# JSON output
network-analyzer json
```

## Development

```bash
pip install pytest
python -m pytest tests/ -v
```

## Requirements

- Python 3.8+
- psutil >= 5.9.0
- dnspython >= 2.4.0

## License

MIT
