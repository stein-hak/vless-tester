# VLESS Connection Tester

A comprehensive Python tool for testing VLESS proxy connections with support for multiple transport protocols. Automatically downloads xray-core, tests connections, and verifies IP changes through each proxy server.

## Features

- **Multiple Transport Support**: gRPC, XHTTP (splithttp), WebSocket, HTTP/2, TCP
- **Security Layers**: TLS and REALITY protocol support
- **Flexible Input Methods**:
  - Single VLESS link testing
  - File-based bulk testing (extracts vless:// URIs from any file format)
  - Subscription URL support (base64-encoded)
- **Automatic Xray Management**: Downloads and installs xray-core automatically
- **Reliable IP Verification**: Uses multiple IP check services with automatic fallback for robust connectivity testing
- **Speedtest Integration**: Optional speed testing (download/upload/ping) for each connection using speedtest-cli
- **Multiple Output Formats**: Human-readable or JSON for automation
- **Cross-Platform**: Works on Linux, macOS, and Windows

## Requirements

- Python 3.7+
- Internet connection
- No admin/root privileges required

## Installation

### 1. Clone the repository

```bash
git clone <repository-url>
cd vless-tester
```

### 2. Create virtual environment (recommended)

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

## Quick Start

### Test a single VLESS connection

```bash
python vless_tester.py --link "vless://uuid@server:port?type=tcp&security=tls#MyServer"
```

### Test from a subscription URL

```bash
python vless_tester.py --subscription https://example.com/sub/your-subscription
```

### Test from a file

```bash
python vless_tester.py --file servers.txt
```

## Usage

### Command-Line Options

```
Options:
  --file <file>            File containing VLESS links (any format - txt, json, etc.)
  --subscription <url>     Subscription URL (base64 encoded)
  --link <vless://...>     Single VLESS link to test
  --speedtest              Run speedtest (download/upload/ping) for each connection
  --json                   Output results in JSON format for machine parsing
  --quiet                  Suppress info messages (useful with --json)
  -h, --help              Show help message
```

### Examples

#### Test multiple files and a subscription

```bash
python vless_tester.py --file servers1.txt --file servers2.json --subscription https://sub.example.com
```

#### JSON output for automation

```bash
python vless_tester.py --subscription https://example.com/sub --json --quiet > results.json
```

#### Test specific server

```bash
python vless_tester.py --link "vless://542cc7c8-6bf6-41d4-8672-435899129974a@server.example.com:443?encryption=none&security=tls&type=grpc&serviceName=sync#MyGrpcServer"
```

#### Run speedtest on all servers in subscription

```bash
python vless_tester.py --subscription https://example.com/sub --speedtest
```

#### Speedtest with JSON output

```bash
python vless_tester.py --file servers.txt --speedtest --json --quiet > speedtest_results.json
```

## Supported Protocols

### Transport Types

| Transport | Parameter | Description |
|-----------|-----------|-------------|
| **TCP** | `type=tcp` | Standard TCP connection, optionally with HTTP header obfuscation |
| **gRPC** | `type=grpc` | gRPC transport with configurable service name |
| **XHTTP** | `type=xhttp` | HTTP splitting transport (also known as splithttp) |
| **WebSocket** | `type=ws` | WebSocket transport with custom paths |
| **HTTP/2** | `type=http` or `type=h2` | HTTP/2 transport |

### Security Layers

| Security | Parameter | Description |
|----------|-----------|-------------|
| **None** | `security=none` | No encryption (not recommended) |
| **TLS** | `security=tls` | Standard TLS encryption |
| **REALITY** | `security=reality` | REALITY protocol with anti-detection |

### Transport-Specific Parameters

#### gRPC
- `serviceName`: gRPC service name (e.g., `sync`, `grpc`)
- `mode`: Operation mode (`gun`, `multi`)

#### XHTTP/WebSocket/HTTP
- `path`: Request path (e.g., `/api`, `/ws`)
- `host`: Host header value

#### TLS/REALITY
- `sni`: Server Name Indication
- `fp`: Fingerprint (e.g., `chrome`, `firefox`)
- `alpn`: Application-Layer Protocol Negotiation

#### REALITY-Specific
- `pbk`: Public key
- `sid`: Short ID
- `spx`: Spider X path

## VLESS Link Format

Standard VLESS URI format:

```
vless://UUID@ADDRESS:PORT?param1=value1&param2=value2#NAME
```

### Example Links

**gRPC + TLS:**
```
vless://542cc7c8-6bf6-41d4-8672-435899129974a@server.com:443?encryption=none&security=tls&type=grpc&serviceName=sync#gRPC-Server
```

**XHTTP + TLS:**
```
vless://542cc7c8-6bf6-41d4-8672-435899129974a@server.com:443?encryption=none&security=tls&type=xhttp&path=/api#XHTTP-Server
```

**TCP + REALITY:**
```
vless://uuid@server.com:443?type=tcp&security=reality&fp=chrome&pbk=publickey&sid=shortid&sni=example.com&flow=xtls-rprx-vision#REALITY-Server
```

## Output Formats

### Human-Readable Output (Default)

```
============================================================
Starting VLESS Connection Tests
Total connections to test: 2
============================================================

[1/2] Testing Server 1...
[INFO] Current IP: 1.2.3.4
[INFO] Proxy IP: 5.6.7.8
[SUCCESS] IP changed: 1.2.3.4 -> 5.6.7.8

============================================================
TEST SUMMARY
============================================================

Total tests: 2
Successful: 2
Failed: 0
Success rate: 100.0%

Name                           Status     Original IP     Proxy IP
----------------------------------------------------------------------
Server 1                       OK         1.2.3.4         5.6.7.8
Server 2                       OK         1.2.3.4         9.10.11.12
```

### JSON Output (`--json`)

```json
{
  "total": 2,
  "successful": 2,
  "failed": 0,
  "success_rate": 100.0,
  "results": [
    {
      "name": "Server 1",
      "address": "server1.example.com",
      "port": 443,
      "success": true,
      "original_ip": "1.2.3.4",
      "proxy_ip": "5.6.7.8",
      "ip_changed": true,
      "error": null,
      "download_mbps": null,
      "upload_mbps": null,
      "ping_ms": null,
      "speedtest_error": null
    }
  ]
}
```

### Speedtest Output (`--speedtest`)

When `--speedtest` is enabled, the output includes speed metrics:

```
============================================================
TEST SUMMARY
============================================================

Total tests: 3
Successful: 3
Failed: 0
Success rate: 100.0%

Name                           Status   Download     Upload       Ping
------------------------------------------------------------------------
Server 1                       OK       125.3 Mbps   45.2 Mbps    28.0 ms
Server 2                       OK       98.7 Mbps    38.1 Mbps    85.0 ms
Server 3                       OK       156.2 Mbps   52.8 Mbps    12.0 ms
```

**JSON with speedtest:**
```json
{
  "name": "Server 1",
  "success": true,
  "download_mbps": 125.3,
  "upload_mbps": 45.2,
  "ping_ms": 28.0,
  "speedtest_error": null
}
```

**Notes**:
- Speedtest adds approximately 20-30 seconds per server for download and upload testing
- Speedtest.net may rate limit requests - if you see HTTP 403 errors, wait a few minutes before retrying
- Testing many servers in quick succession may trigger temporary rate limits

## How It Works

1. **Parse Input**: Extracts VLESS URIs from links, files, or subscriptions
2. **Download Xray**: Automatically downloads the appropriate xray-core binary for your platform
3. **Generate Config**: Creates xray configuration with proper transport settings
4. **Test Connection**:
   - Gets your original IP using multiple services (icanhazip.com, ipify.org, checkip.amazonaws.com, etc.) with automatic fallback
   - Starts xray with the VLESS configuration
   - Requests IP through the proxy using the same multi-service approach
   - Verifies IP has changed
5. **Report Results**: Displays test results in chosen format

The tool uses 6 different IP check services to ensure reliable testing even if some services are down or rate-limited.

## File Input Formats

The tool can extract VLESS links from any text-based file:

### Plain Text File (servers.txt)
```
vless://uuid1@server1:443?params#Server1
vless://uuid2@server2:443?params#Server2
```

### JSON File (servers.json)
```json
[
  {
    "name": "Server 1",
    "uri": "vless://uuid@server:443?params#Name"
  }
]
```

The tool uses regex to find all `vless://` URIs regardless of file format.

## Subscription Support

Subscriptions are typically base64-encoded lists of VLESS links:

```bash
# Fetch subscription
curl https://example.com/sub/token

# Returns base64-encoded content like:
dmxlc3M6Ly91dWlkQHNlcnZlcjE6NDQzP3BhcmFtcyNTZXJ2ZXIK...

# Decoded:
vless://uuid@server1:443?params#Server1
vless://uuid@server2:443?params#Server2
```

The tool automatically handles decoding and parsing.

## Platform Support

The tool automatically detects your platform and downloads the correct xray-core binary:

| OS | Architectures |
|----|---------------|
| **Linux** | x86_64, ARM64, ARMv7, i386 |
| **macOS** | x86_64, ARM64 (Apple Silicon) |
| **Windows** | x86_64, i386 |

## Troubleshooting

### Connection Test Fails

**Problem**: Tests show "Failed to get IP through proxy"

**Solutions**:
- Check if the VLESS server is actually reachable
- Verify the configuration parameters (UUID, security settings)
- Try testing with a different server
- Check your firewall settings

### Xray Download Fails

**Problem**: Cannot download xray-core

**Solutions**:
- Check your internet connection
- Verify GitHub API is accessible
- Download manually from [Xray releases](https://github.com/XTLS/Xray-core/releases) and place in `./xray/` directory

### IP Doesn't Change

**Problem**: Test reports "IP did not change"

**Solutions**:
- Server might be misconfigured or offline
- Check if server parameters are correct
- Verify security settings (TLS certificates, REALITY keys)

### Import Errors

**Problem**: `ModuleNotFoundError`

**Solutions**:
```bash
# Ensure virtual environment is activated
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

### Speedtest HTTP 403 Errors

**Problem**: `[ERROR] Speedtest failed: HTTP Error 403: Forbidden`

**Cause**: Speedtest.net implements rate limiting to prevent abuse

**Solutions**:
- Wait 5-10 minutes before running speedtest again
- Reduce the number of servers tested at once
- Test servers in smaller batches with delays between batches
- The connection test (IP change verification) still works - only speedtest is affected

**Note**: This is expected behavior when testing many servers quickly. The rate limit typically clears after a short wait.

## Advanced Usage

### Testing Specific Transport Types

Extract and test only gRPC servers:
```bash
python vless_tester.py --subscription https://sub.example.com --json --quiet | \
  jq '.results[] | select(.success == true)' | \
  jq -s 'map(select(.name | contains("gRPC")))'
```

### Automation with Cron

Test servers daily and save results:
```bash
#!/bin/bash
# Daily server test script
cd /path/to/vless-tester
source venv/bin/activate
python vless_tester.py \
  --subscription https://example.com/sub \
  --json --quiet > "results_$(date +%Y%m%d).json"
```

### Parallel Testing with Multiple Subscriptions

```bash
python vless_tester.py \
  --subscription https://provider1.com/sub \
  --subscription https://provider2.com/sub \
  --file local_servers.txt \
  --json
```

## Exit Codes

- `0`: All tests successful
- `1`: One or more tests failed

Useful for scripting:
```bash
if python vless_tester.py --file servers.txt; then
  echo "All servers working!"
else
  echo "Some servers failed"
fi
```

## Security Considerations

- VLESS links contain sensitive UUIDs and server information
- Store subscription URLs and configuration files securely
- Use `.gitignore` to avoid committing sensitive data
- The tool only tests connections and doesn't log traffic

## Contributing

Contributions are welcome! Areas for improvement:
- Additional transport protocols
- Performance optimizations
- Better error handling
- Unit tests

## License

This project is provided as-is for educational and testing purposes.

## Acknowledgments

- [Xray-core](https://github.com/XTLS/Xray-core) - The underlying proxy engine
- VLESS protocol developers
