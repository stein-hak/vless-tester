#!/usr/bin/env python3
"""
VLESS Connection Tester
Tests multiple VLESS connections using xray and verifies IP changes
"""

import json
import subprocess
import time
import requests
import tempfile
import os
import sys
import platform
import zipfile
import stat
import base64
import urllib.parse
import re
from typing import Dict, Optional, List
from dataclasses import dataclass
from pathlib import Path

try:
    import speedtest
except ImportError:
    speedtest = None


@dataclass
class VLESSConfig:
    """VLESS connection configuration"""
    name: str
    address: str
    port: int
    uuid: str
    encryption: str = "none"
    flow: str = ""
    network: str = "tcp"
    security: str = "none"
    sni: str = ""
    alpn: List[str] = None
    fingerprint: str = ""
    # REALITY-specific parameters
    pbk: str = ""  # Public key
    sid: str = ""  # Short ID
    spx: str = ""  # Spider X / Path
    # Transport-specific parameters
    path: str = ""  # For HTTP/XHTTP/WebSocket
    host: str = ""  # For HTTP/XHTTP/WebSocket headers
    serviceName: str = ""  # For gRPC
    mode: str = ""  # For gRPC/HTTP (gun, multi, etc.)

    def __post_init__(self):
        if self.alpn is None:
            self.alpn = []


class XrayDownloader:
    """Handle xray binary download and management"""

    XRAY_RELEASES_URL = "https://api.github.com/repos/XTLS/Xray-core/releases/latest"

    def __init__(self, install_dir: str = "./xray", quiet: bool = False):
        self.install_dir = Path(install_dir)
        self.install_dir.mkdir(exist_ok=True)
        self.quiet = quiet

    def log(self, message: str):
        """Print message unless in quiet mode"""
        if not self.quiet:
            print(message)

    def get_platform_info(self) -> tuple:
        """Get current platform information"""
        system = platform.system().lower()
        machine = platform.machine().lower()

        # Map system name
        if system == "linux":
            os_name = "linux"
        elif system == "darwin":
            os_name = "macos"
        elif system == "windows":
            os_name = "windows"
        else:
            raise Exception(f"Unsupported operating system: {system}")

        # Map architecture
        if machine in ["x86_64", "amd64"]:
            arch = "64"
        elif machine in ["aarch64", "arm64"]:
            arch = "arm64-v8a"
        elif machine in ["armv7l", "armv7"]:
            arch = "arm32-v7a"
        elif machine in ["i386", "i686"]:
            arch = "32"
        else:
            raise Exception(f"Unsupported architecture: {machine}")

        return os_name, arch

    def get_xray_path(self) -> Path:
        """Get the expected path for xray binary"""
        if platform.system().lower() == "windows":
            return self.install_dir / "xray.exe"
        else:
            return self.install_dir / "xray"

    def is_xray_installed(self) -> bool:
        """Check if xray is already installed"""
        xray_path = self.get_xray_path()
        return xray_path.exists() and os.access(xray_path, os.X_OK)

    def download_xray(self) -> bool:
        """Download and install xray binary"""
        try:
            self.log("[INFO] Checking for xray binary...")

            if self.is_xray_installed():
                self.log(f"[INFO] xray already installed at {self.get_xray_path()}")
                return True

            self.log("[INFO] xray not found, downloading...")

            # Get platform info
            os_name, arch = self.get_platform_info()
            self.log(f"[INFO] Detected platform: {os_name}-{arch}")

            # Get latest release info
            self.log("[INFO] Fetching latest xray release...")
            response = requests.get(self.XRAY_RELEASES_URL, timeout=30)
            response.raise_for_status()
            release_data = response.json()

            # Find appropriate asset
            asset_name = f"Xray-{os_name}-{arch}.zip"
            download_url = None

            for asset in release_data.get("assets", []):
                if asset["name"] == asset_name:
                    download_url = asset["browser_download_url"]
                    break

            if not download_url:
                print(f"[ERROR] Could not find release for {asset_name}")
                print("[INFO] Available assets:")
                for asset in release_data.get("assets", []):
                    print(f"  - {asset['name']}")
                return False

            # Download the zip file
            self.log(f"[INFO] Downloading {asset_name}...")
            zip_path = self.install_dir / asset_name

            response = requests.get(download_url, timeout=120, stream=True)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0 and not self.quiet:
                        percent = (downloaded / total_size) * 100
                        print(f"\r[INFO] Progress: {percent:.1f}%", end='', flush=True)

            self.log("\n[INFO] Download complete")

            # Extract the zip file
            self.log("[INFO] Extracting xray...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.install_dir)

            # Make xray executable on Unix-like systems
            xray_path = self.get_xray_path()
            if platform.system().lower() != "windows":
                os.chmod(xray_path, os.stat(xray_path).st_mode | stat.S_IEXEC)

            # Clean up zip file
            zip_path.unlink()

            # Verify installation
            if self.is_xray_installed():
                self.log(f"[SUCCESS] xray installed successfully at {xray_path}")
                return True
            else:
                self.log("[ERROR] xray installation failed")
                return False

        except Exception as e:
            self.log(f"[ERROR] Failed to download xray: {e}")
            return False


class VLESSTester:
    """Main class for testing VLESS connections"""

    # Multiple IP check services for reliability
    IP_CHECK_SERVICES = [
        "http://icanhazip.com",
        "http://api.ipify.org",
        "http://checkip.amazonaws.com",
        "http://ipecho.net/plain",
        "http://ifconfig.me",
        "http://ident.me"
    ]

    def __init__(self, xray_path: str = None, timeout: int = 10, proxy_port: int = 10808, quiet: bool = False, run_speedtest: bool = False):
        self.xray_path = xray_path
        self.timeout = timeout
        self.proxy_port = proxy_port
        self.xray_process: Optional[subprocess.Popen] = None
        self.config_file: Optional[str] = None
        self.quiet = quiet
        self.run_speedtest = run_speedtest

    def log(self, message: str):
        """Print message unless in quiet mode"""
        if not self.quiet:
            print(message)

    def get_current_ip(self) -> Optional[str]:
        """Get current public IP address using multiple services with fallback"""
        for service in self.IP_CHECK_SERVICES:
            try:
                response = requests.get(service, timeout=self.timeout)
                if response.status_code == 200:
                    ip = response.text.strip()
                    self.log(f"[INFO] Current IP: {ip} (via {service})")
                    return ip
            except Exception as e:
                # Try next service if this one fails
                continue

        # All services failed
        self.log(f"[ERROR] Failed to get current IP from all services")
        return None

    def get_ip_through_proxy(self) -> Optional[str]:
        """Get IP address through the proxy using multiple services with fallback"""
        proxies = {
            'http': f'socks5://127.0.0.1:{self.proxy_port}',
            'https': f'socks5://127.0.0.1:{self.proxy_port}'
        }

        for service in self.IP_CHECK_SERVICES:
            try:
                response = requests.get(service,
                                      proxies=proxies,
                                      timeout=self.timeout)
                if response.status_code == 200:
                    ip = response.text.strip()
                    self.log(f"[INFO] Proxy IP: {ip} (via {service})")
                    return ip
            except Exception as e:
                # Try next service if this one fails
                continue

        # All services failed
        self.log(f"[ERROR] Failed to get IP through proxy from all services")
        return None

    def run_speedtest_through_proxy(self) -> Dict:
        """Run speedtest through the proxy"""
        result = {
            "download_mbps": None,
            "upload_mbps": None,
            "ping_ms": None,
            "speedtest_error": None
        }

        if speedtest is None:
            result["speedtest_error"] = "speedtest-cli not installed"
            self.log("[WARNING] speedtest-cli not installed, skipping speedtest")
            return result

        try:
            self.log("[INFO] Running speedtest through proxy...")

            # Configure speedtest to use proxy
            os.environ['http_proxy'] = f'socks5://127.0.0.1:{self.proxy_port}'
            os.environ['https_proxy'] = f'socks5://127.0.0.1:{self.proxy_port}'

            # Create speedtest client
            st = speedtest.Speedtest()

            # Get best server based on ping
            self.log("[INFO] Finding best server...")
            st.get_best_server()

            # Run download test
            self.log("[INFO] Testing download speed...")
            download_bps = st.download()
            result["download_mbps"] = round(download_bps / 1_000_000, 2)

            # Run upload test
            self.log("[INFO] Testing upload speed...")
            upload_bps = st.upload()
            result["upload_mbps"] = round(upload_bps / 1_000_000, 2)

            # Get ping
            result["ping_ms"] = round(st.results.ping, 2)

            self.log(f"[INFO] Speedtest results: ↓ {result['download_mbps']} Mbps, ↑ {result['upload_mbps']} Mbps, Ping: {result['ping_ms']} ms")

            # Clean up proxy env vars
            if 'http_proxy' in os.environ:
                del os.environ['http_proxy']
            if 'https_proxy' in os.environ:
                del os.environ['https_proxy']

        except Exception as e:
            result["speedtest_error"] = str(e)
            self.log(f"[ERROR] Speedtest failed: {e}")

            # Clean up proxy env vars on error
            if 'http_proxy' in os.environ:
                del os.environ['http_proxy']
            if 'https_proxy' in os.environ:
                del os.environ['https_proxy']

        return result

    def create_xray_config(self, vless_config: VLESSConfig) -> Dict:
        """Create xray configuration for VLESS connection"""

        # Build stream settings
        stream_settings = {
            "network": vless_config.network
        }

        if vless_config.security in ["tls", "reality"]:
            if vless_config.security == "tls":
                stream_settings["security"] = "tls"
                stream_settings["tlsSettings"] = {
                    "serverName": vless_config.sni,
                    "alpn": vless_config.alpn if vless_config.alpn else [],
                    "fingerprint": vless_config.fingerprint if vless_config.fingerprint else ""
                }
            elif vless_config.security == "reality":
                stream_settings["security"] = "reality"
                reality_settings = {
                    "serverName": vless_config.sni,
                    "fingerprint": vless_config.fingerprint if vless_config.fingerprint else "chrome",
                    "show": False
                }
                # Add REALITY-specific parameters if present
                if vless_config.pbk:
                    reality_settings["publicKey"] = vless_config.pbk
                if vless_config.sid:
                    reality_settings["shortId"] = vless_config.sid
                if vless_config.spx:
                    reality_settings["spiderX"] = vless_config.spx
                stream_settings["realitySettings"] = reality_settings

        # Add transport-specific settings
        if vless_config.network == "grpc":
            grpc_settings = {}
            if vless_config.serviceName:
                grpc_settings["serviceName"] = vless_config.serviceName
            if vless_config.mode:
                grpc_settings["multiMode"] = (vless_config.mode == "multi")
            stream_settings["grpcSettings"] = grpc_settings

        elif vless_config.network == "ws":
            ws_settings = {}
            if vless_config.path:
                ws_settings["path"] = vless_config.path
            if vless_config.host:
                ws_settings["headers"] = {"Host": vless_config.host}
            stream_settings["wsSettings"] = ws_settings

        elif vless_config.network == "http" or vless_config.network == "h2":
            http_settings = {}
            if vless_config.path:
                http_settings["path"] = vless_config.path
            if vless_config.host:
                http_settings["host"] = [vless_config.host]
            stream_settings["httpSettings"] = http_settings

        elif vless_config.network == "xhttp" or vless_config.network == "splithttp":
            # XHTTP is also known as splithttp in xray
            splithttp_settings = {}
            if vless_config.path:
                splithttp_settings["path"] = vless_config.path
            if vless_config.host:
                splithttp_settings["host"] = vless_config.host
            if vless_config.mode:
                splithttp_settings["mode"] = vless_config.mode
            stream_settings["splithttpSettings"] = splithttp_settings

        elif vless_config.network == "tcp":
            # TCP can have header settings
            if vless_config.path or vless_config.host:
                tcp_settings = {
                    "header": {
                        "type": "http",
                        "request": {}
                    }
                }
                if vless_config.path:
                    tcp_settings["header"]["request"]["path"] = [vless_config.path]
                if vless_config.host:
                    tcp_settings["header"]["request"]["headers"] = {"Host": [vless_config.host]}
                stream_settings["tcpSettings"] = tcp_settings

        # Build VLESS outbound
        outbound = {
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": vless_config.address,
                    "port": vless_config.port,
                    "users": [{
                        "id": vless_config.uuid,
                        "encryption": vless_config.encryption
                    }]
                }]
            },
            "streamSettings": stream_settings
        }

        # Add flow if specified
        if vless_config.flow:
            outbound["settings"]["vnext"][0]["users"][0]["flow"] = vless_config.flow

        # Complete xray config
        config = {
            "log": {
                "loglevel": "warning"
            },
            "inbounds": [{
                "port": self.proxy_port,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": {
                    "udp": True
                }
            }],
            "outbounds": [outbound]
        }

        return config

    def start_xray(self, vless_config: VLESSConfig) -> bool:
        """Start xray with the given VLESS configuration"""
        try:
            # Create temporary config file
            config = self.create_xray_config(vless_config)

            # Create temp file
            fd, self.config_file = tempfile.mkstemp(suffix='.json', prefix='xray_')
            with os.fdopen(fd, 'w') as f:
                json.dump(config, f, indent=2)

            self.log(f"[INFO] Starting xray with config: {vless_config.name}")

            # Start xray process
            self.xray_process = subprocess.Popen(
                [self.xray_path, "run", "-c", self.config_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Wait a bit for xray to start
            time.sleep(2)

            # Check if process is still running
            if self.xray_process.poll() is not None:
                _, stderr = self.xray_process.communicate()
                self.log(f"[ERROR] xray failed to start: {stderr}")
                return False

            self.log("[INFO] xray started successfully")
            return True

        except Exception as e:
            self.log(f"[ERROR] Failed to start xray: {e}")
            return False

    def stop_xray(self):
        """Stop the xray process"""
        if self.xray_process:
            self.log("[INFO] Stopping xray...")
            self.xray_process.terminate()
            try:
                self.xray_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.xray_process.kill()
            self.xray_process = None

        # Clean up config file
        if self.config_file and os.path.exists(self.config_file):
            os.unlink(self.config_file)
            self.config_file = None

    def test_connection(self, vless_config: VLESSConfig) -> Dict:
        """Test a single VLESS connection"""
        result = {
            "name": vless_config.name,
            "address": vless_config.address,
            "port": vless_config.port,
            "success": False,
            "original_ip": None,
            "proxy_ip": None,
            "ip_changed": False,
            "error": None,
            "download_mbps": None,
            "upload_mbps": None,
            "ping_ms": None,
            "speedtest_error": None
        }

        self.log(f"\n{'='*60}")
        self.log(f"Testing connection: {vless_config.name}")
        self.log(f"{'='*60}")

        try:
            # Get original IP
            original_ip = self.get_current_ip()
            if not original_ip:
                result["error"] = "Failed to get original IP"
                return result
            result["original_ip"] = original_ip

            # Start xray
            if not self.start_xray(vless_config):
                result["error"] = "Failed to start xray"
                return result

            # Wait a bit more for connection to establish
            time.sleep(3)

            # Get IP through proxy
            proxy_ip = self.get_ip_through_proxy()
            if not proxy_ip:
                result["error"] = "Failed to get IP through proxy"
                return result
            result["proxy_ip"] = proxy_ip

            # Check if IP changed
            result["ip_changed"] = original_ip != proxy_ip
            result["success"] = result["ip_changed"]

            if result["ip_changed"]:
                self.log(f"[SUCCESS] IP changed: {original_ip} -> {proxy_ip}")

                # Run speedtest if requested
                if self.run_speedtest:
                    speedtest_result = self.run_speedtest_through_proxy()
                    result["download_mbps"] = speedtest_result["download_mbps"]
                    result["upload_mbps"] = speedtest_result["upload_mbps"]
                    result["ping_ms"] = speedtest_result["ping_ms"]
                    result["speedtest_error"] = speedtest_result["speedtest_error"]
            else:
                self.log(f"[WARNING] IP did not change (still {original_ip})")

        except Exception as e:
            result["error"] = str(e)
            self.log(f"[ERROR] Test failed: {e}")
        finally:
            self.stop_xray()

        return result

    def test_multiple_connections(self, vless_configs: List[VLESSConfig], json_output: bool = False) -> List[Dict]:
        """Test multiple VLESS connections"""
        results = []

        self.log(f"\n{'='*60}")
        self.log(f"Starting VLESS Connection Tests")
        self.log(f"Total connections to test: {len(vless_configs)}")
        self.log(f"{'='*60}")

        for i, config in enumerate(vless_configs, 1):
            self.log(f"\n[{i}/{len(vless_configs)}] Testing {config.name}...")
            result = self.test_connection(config)
            results.append(result)

            # Small delay between tests
            if i < len(vless_configs):
                time.sleep(2)

        # Print summary (only in non-JSON mode)
        if not json_output:
            self.print_summary(results)

        return results

    def print_summary(self, results: List[Dict]):
        """Print test summary"""
        print(f"\n{'='*60}")
        print("TEST SUMMARY")
        print(f"{'='*60}")

        successful = sum(1 for r in results if r["success"])
        total = len(results)

        print(f"\nTotal tests: {total}")
        print(f"Successful: {successful}")
        print(f"Failed: {total - successful}")
        print(f"Success rate: {successful/total*100:.1f}%")

        # Check if any results have speedtest data
        has_speedtest = any(r.get("download_mbps") is not None for r in results)

        if has_speedtest:
            # Include speedtest columns
            print(f"\n{'Name':<30} {'Status':<8} {'Download':<12} {'Upload':<12} {'Ping':<10}")
            print("-" * 72)

            for result in results:
                status = "OK" if result["success"] else "FAIL"
                name = result["name"][:29]

                download = f"{result.get('download_mbps', 0):.1f} Mbps" if result.get('download_mbps') else "N/A"
                upload = f"{result.get('upload_mbps', 0):.1f} Mbps" if result.get('upload_mbps') else "N/A"
                ping = f"{result.get('ping_ms', 0):.1f} ms" if result.get('ping_ms') else "N/A"

                print(f"{name:<30} {status:<8} {download:<12} {upload:<12} {ping:<10}")
                if result.get("error"):
                    print(f"  Error: {result['error']}")
                if result.get("speedtest_error"):
                    print(f"  Speedtest Error: {result['speedtest_error']}")
        else:
            # Original format without speedtest
            print(f"\n{'Name':<30} {'Status':<10} {'Original IP':<15} {'Proxy IP':<15}")
            print("-" * 70)

            for result in results:
                status = "OK" if result["success"] else "FAIL"
                original = result.get("original_ip", "N/A") or "N/A"
                proxy = result.get("proxy_ip", "N/A") or "N/A"
                name = result["name"][:29]

                print(f"{name:<30} {status:<10} {original:<15} {proxy:<15}")
                if result.get("error"):
                    print(f"  Error: {result['error']}")


def parse_vless_link(link: str) -> Optional[VLESSConfig]:
    """Parse a VLESS link into VLESSConfig"""
    try:
        if not link.startswith("vless://"):
            return None

        # Remove vless:// prefix
        link = link[8:]

        # Split fragment (name) if present
        if '#' in link:
            link, name = link.split('#', 1)
            name = urllib.parse.unquote(name)
        else:
            name = "Unnamed"

        # Split query parameters
        if '?' in link:
            address_part, query_part = link.split('?', 1)
            params = urllib.parse.parse_qs(query_part)
        else:
            address_part = link
            params = {}

        # Parse address part: uuid@address:port
        if '@' not in address_part:
            print(f"[ERROR] Invalid VLESS link format: missing @")
            return None

        uuid, server_part = address_part.split('@', 1)

        if ':' not in server_part:
            print(f"[ERROR] Invalid VLESS link format: missing port")
            return None

        address, port_str = server_part.rsplit(':', 1)
        port = int(port_str)

        # Parse parameters
        encryption = params.get('encryption', ['none'])[0]
        flow = params.get('flow', [''])[0]
        network = params.get('type', ['tcp'])[0]
        security = params.get('security', ['none'])[0]
        sni = params.get('sni', [''])[0]
        fingerprint = params.get('fp', [''])[0]

        # Parse ALPN
        alpn_str = params.get('alpn', [''])[0]
        alpn = alpn_str.split(',') if alpn_str else []

        # Parse REALITY-specific parameters
        pbk = params.get('pbk', [''])[0]
        sid = params.get('sid', [''])[0]
        spx = params.get('spx', [''])[0]

        # Parse transport-specific parameters
        path = params.get('path', [''])[0]
        host = params.get('host', [''])[0]
        serviceName = params.get('serviceName', [''])[0]
        mode = params.get('mode', [''])[0]

        config = VLESSConfig(
            name=name,
            address=address,
            port=port,
            uuid=uuid,
            encryption=encryption,
            flow=flow,
            network=network,
            security=security,
            sni=sni,
            alpn=alpn,
            fingerprint=fingerprint,
            pbk=pbk,
            sid=sid,
            spx=spx,
            path=path,
            host=host,
            serviceName=serviceName,
            mode=mode
        )

        return config

    except Exception as e:
        print(f"[ERROR] Failed to parse VLESS link: {e}")
        return None


def load_vless_links_from_file(filepath: str, quiet: bool = False) -> List[VLESSConfig]:
    """Load VLESS links from any file (extracts vless:// URIs)"""
    configs = []

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # Extract all vless:// links from the file content
        # Find all occurrences of vless:// followed by non-whitespace characters
        vless_pattern = r'vless://[^\s\'"<>]+'
        matches = re.findall(vless_pattern, content)

        if not quiet:
            print(f"[INFO] Found {len(matches)} VLESS link(s) in file")

        for link in matches:
            config = parse_vless_link(link)
            if config:
                configs.append(config)

    except Exception as e:
        print(f"[ERROR] Failed to load VLESS links from file: {e}")

    return configs


def fetch_subscription(url: str) -> List[VLESSConfig]:
    """Fetch and parse VLESS subscription from URL"""
    configs = []

    try:
        print(f"[INFO] Fetching subscription from: {url}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # Subscription content is typically base64 encoded
        content = response.text.strip()

        # Try to decode base64
        try:
            decoded = base64.b64decode(content).decode('utf-8')
        except Exception:
            # If base64 decode fails, assume it's already plain text
            decoded = content

        # Parse each line
        for line in decoded.split('\n'):
            line = line.strip()
            if line and line.startswith('vless://'):
                config = parse_vless_link(line)
                if config:
                    configs.append(config)

        print(f"[INFO] Found {len(configs)} VLESS configurations in subscription")

    except Exception as e:
        print(f"[ERROR] Failed to fetch subscription: {e}")

    return configs




def print_usage():
    """Print usage information"""
    print("""
Usage:
  python vless_tester.py [OPTIONS]

Options:
  --file <file>            File containing VLESS links (any format - txt, json, etc.)
  --subscription <url>     Subscription URL (base64 encoded)
  --link <vless://...>     Single VLESS link to test
  --speedtest              Run speedtest (download/upload/ping) for each connection
  --json                   Output results in JSON format for machine parsing
  --quiet                  Suppress info messages (useful with --json)

Examples:
  python vless_tester.py --file vless_links.txt
  python vless_tester.py --file servers.json
  python vless_tester.py --subscription https://example.com/sub
  python vless_tester.py --link "vless://uuid@server:port?..."
  python vless_tester.py --file servers.json --json --quiet
  python vless_tester.py --subscription https://example.com/sub --speedtest

You can combine multiple sources:
  python vless_tester.py --file file1.txt --file file2.json --subscription https://sub.url

Note: The script extracts all vless:// URIs from any file format (text, JSON, etc.)
""")


def main():
    """Main function"""

    # Parse command line arguments - first pass for flags
    json_output = False
    quiet = False
    run_speedtest = False
    files = []
    subscriptions = []
    links = []

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]

        if arg in ['-h', '--help']:
            print_usage()
            sys.exit(0)

        elif arg == '--json':
            json_output = True
            i += 1

        elif arg == '--quiet':
            quiet = True
            i += 1

        elif arg == '--speedtest':
            run_speedtest = True
            i += 1

        elif arg in ['--file', '--links-file', '-f']:
            if i + 1 >= len(sys.argv):
                print("[ERROR] --file requires a file path")
                sys.exit(1)
            files.append(sys.argv[i + 1])
            i += 2

        elif arg == '--subscription':
            if i + 1 >= len(sys.argv):
                print("[ERROR] --subscription requires a URL")
                sys.exit(1)
            subscriptions.append(sys.argv[i + 1])
            i += 2

        elif arg == '--link':
            if i + 1 >= len(sys.argv):
                print("[ERROR] --link requires a VLESS URL")
                sys.exit(1)
            links.append(sys.argv[i + 1])
            i += 2

        else:
            print(f"[ERROR] Unknown argument: {arg}")
            print_usage()
            sys.exit(1)

    # Load configs after parsing all flags
    configs = []

    for filepath in files:
        if not quiet:
            print(f"[INFO] Loading VLESS links from: {filepath}")
        configs.extend(load_vless_links_from_file(filepath, quiet=quiet))

    for url in subscriptions:
        configs.extend(fetch_subscription(url))

    for link in links:
        config = parse_vless_link(link)
        if config:
            configs.append(config)
        else:
            print(f"[ERROR] Failed to parse VLESS link")
            sys.exit(1)

    if not quiet:
        print("VLESS Connection Tester")
        print("="*60)

    # Setup xray
    downloader = XrayDownloader(quiet=quiet)
    if not downloader.download_xray():
        print("[ERROR] Failed to setup xray")
        sys.exit(1)

    xray_path = str(downloader.get_xray_path())

    # If no configs loaded, show usage
    if not configs:
        print("\n[WARNING] No VLESS configurations provided")
        print_usage()
        sys.exit(1)

    if not quiet:
        print(f"\n[INFO] Loaded {len(configs)} VLESS configuration(s)")

    # Create tester instance
    tester = VLESSTester(xray_path=xray_path, timeout=10, proxy_port=10808, quiet=quiet, run_speedtest=run_speedtest)

    # Run tests
    results = tester.test_multiple_connections(configs, json_output=json_output)

    # Output results
    if json_output:
        output = {
            "total": len(results),
            "successful": sum(1 for r in results if r["success"]),
            "failed": sum(1 for r in results if not r["success"]),
            "success_rate": sum(1 for r in results if r["success"]) / len(results) * 100 if results else 0,
            "results": results
        }
        print(json.dumps(output, indent=2))

    # Exit with appropriate code
    successful = sum(1 for r in results if r["success"])
    sys.exit(0 if successful == len(results) else 1)


if __name__ == "__main__":
    main()
