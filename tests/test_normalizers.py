"""One test per source normalizer, using the real sample payloads from
samples/ (not hand-crafted fixtures) so a change to the samples that
breaks a field mapping is caught here. Every field the normalizer sets is
asserted. The two syslog-based sources (firewall, network) go through
parse_syslog_line first, exactly as ingest/syslog_server.py's
handle_message does before calling normalize().
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from ingest.normalizers import ad, api, aws, crowdstrike, firewall, m365, network
from ingest.syslog_parser import parse_syslog_line

SAMPLES = Path(__file__).parent.parent / "samples"


def _load_json(name: str) -> dict:
    return json.loads((SAMPLES / name).read_text())


def test_normalize_api():
    payload = _load_json("api.json")
    result = api.normalize(payload, tenant="demoA")

    assert result.tenant == "demoA"
    assert result.event_time == datetime(2025, 8, 20, 7, 20, 0, tzinfo=timezone.utc)
    assert result.source == "api"
    assert result.event_type == "app_login_failed"
    assert result.event_subtype == "wrong_password"
    assert str(result.src_ip) == "203.0.113.7"
    assert result.user == "alice"
    assert result.raw == payload


def test_normalize_crowdstrike():
    payload = _load_json("crowdstrike.json")
    result = crowdstrike.normalize(payload, tenant="demoA")

    assert result.tenant == "demoA"
    assert result.event_time == datetime(2025, 8, 20, 8, 0, 0, tzinfo=timezone.utc)
    assert result.source == "crowdstrike"
    assert result.event_type == "malware_detected"
    assert result.severity == 8
    assert result.action == "quarantine"
    assert result.host == "WIN10-01"
    assert result.process == "powershell.exe"
    assert result.raw == payload


def test_normalize_aws():
    payload = _load_json("aws.json")
    result = aws.normalize(payload, tenant="demoB")

    assert result.tenant == "demoB"
    assert result.event_time == datetime(2025, 8, 20, 9, 10, 0, tzinfo=timezone.utc)
    assert result.source == "aws"
    assert result.event_type == "CreateUser"
    assert result.user == "admin"
    assert result.cloud_service == "iam"
    assert result.cloud_account_id == "123456789012"
    assert result.cloud_region == "ap-southeast-1"
    assert result.raw == payload  # includes payload's own nested "raw" key verbatim


def test_normalize_m365():
    payload = _load_json("m365.json")
    result = m365.normalize(payload, tenant="demoB")

    assert result.tenant == "demoB"
    assert result.event_time == datetime(2025, 8, 20, 10, 5, 0, tzinfo=timezone.utc)
    assert result.source == "m365"
    assert result.event_type == "UserLoggedIn"
    assert result.user == "bob@demo.local"
    assert str(result.src_ip) == "198.51.100.23"
    assert result.action == "Success"
    assert result.raw == payload


def test_normalize_ad():
    payload = _load_json("ad.json")
    result = ad.normalize(payload, tenant="demoA")

    assert result.tenant == "demoA"
    assert result.event_time == datetime(2025, 8, 20, 11, 11, 11, tzinfo=timezone.utc)
    assert result.source == "ad"
    assert result.event_type == "LogonFailed"
    assert result.user == "demo\\eve"
    assert result.host == "DC01"
    assert str(result.src_ip) == "203.0.113.77"
    assert result.rule_id == "4625"
    assert result.raw == payload


def test_normalize_firewall():
    line = (SAMPLES / "firewall.log").read_text().rstrip("\n")
    envelope = parse_syslog_line(line, now=datetime(2025, 8, 21, tzinfo=timezone.utc))

    result = firewall.normalize(envelope, tenant="demoA")

    assert result.tenant == "demoA"
    assert result.event_time == datetime(2025, 8, 20, 12, 44, 56, tzinfo=timezone.utc)
    assert result.source == "firewall"
    assert result.vendor == "demo"
    assert result.product == "ngfw"
    assert result.event_type == "traffic"
    assert result.severity == 1  # 7 - syslog_severity(6); docs/DECISIONS.md #4
    assert result.action == "deny"
    assert str(result.src_ip) == "10.0.1.10"
    assert result.src_port == 5353
    assert str(result.dst_ip) == "8.8.8.8"
    assert result.dst_port == 53
    assert result.protocol == "udp"
    assert result.host == "fw01"
    assert result.rule_name == "Block-DNS"
    assert result.raw == {"raw_line": line}


def test_normalize_network():
    line = (SAMPLES / "network.log").read_text().rstrip("\n")
    envelope = parse_syslog_line(line, now=datetime(2025, 8, 21, tzinfo=timezone.utc))

    result = network.normalize(envelope, tenant="demoA")

    assert result.tenant == "demoA"
    assert result.event_time == datetime(2025, 8, 20, 13, 1, 2, tzinfo=timezone.utc)
    assert result.source == "network"
    assert result.event_type == "link-down"
    assert result.event_subtype == "carrier-loss"
    assert result.severity == 1  # 7 - syslog_severity(6)
    assert result.host == "r1"
    assert result.raw == {"raw_line": line}
