#!/usr/bin/env python3
"""Pre-flight checker: validates environment, packages, API keys, and services."""

import shutil
import sys
import os

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m!\033[0m"


def check_python():
    v = sys.version_info
    ok = v >= (3, 11)
    print(f"  {'PASS' if ok else FAIL} Python {v.major}.{v.minor}.{v.micro}" + ("" if ok else " (need 3.11+)"))
    return ok


def check_packages():
    required = [
        "fastapi", "uvicorn", "aiohttp", "aiohttp_socks", "bs4", "phonenumbers",
        "neo4j", "torch", "torch_geometric", "networkx", "numpy", "sklearn",
        "apscheduler", "plotly", "dotenv", "pyhunter", "jinja2", "httpx",
    ]
    all_ok = True
    for pkg in required:
        try:
            __import__(pkg)
            print(f"  {PASS} {pkg}")
        except ImportError:
            print(f"  {FAIL} {pkg} – not installed")
            all_ok = False
    return all_ok


def check_env_keys():
    from dotenv import load_dotenv
    load_dotenv()
    keys = {
        "NUMVERIFY_API_KEY": True,
        "TRUECALLER_API_KEY": True,
        "HUNTER_API_KEY": True,
        "SPIDERFOOT_API_KEY": False,
    }
    all_ok = True
    for key, required in keys.items():
        val = os.getenv(key, "")
        if val:
            print(f"  {PASS} {key} = {'*' * min(len(val), 8)}...")
        elif required:
            print(f"  {FAIL} {key} – missing (required)")
            all_ok = False
        else:
            print(f"  {WARN} {key} – missing (optional)")
    return all_ok


def check_cli_tools():
    tools = ["sherlock", "maigret", "blackbird"]
    all_ok = True
    for tool in tools:
        path = shutil.which(tool)
        if path:
            print(f"  {PASS} {tool} → {path}")
        else:
            print(f"  {WARN} {tool} – not found in PATH (handler will be disabled)")
    return all_ok


def check_neo4j():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            session.run("RETURN 1")
        driver.close()
        print(f"  {PASS} Neo4j at {uri}")
        return True
    except Exception as e:
        print(f"  {FAIL} Neo4j at {uri} – {e}")
        return False


def check_tor():
    import socket
    host = os.getenv("TOR_PROXY_HOST", "localhost")
    port = int(os.getenv("TOR_PROXY_PORT", "9050"))
    try:
        s = socket.create_connection((host, port), timeout=5)
        s.close()
        print(f"  {PASS} Tor SOCKS5 at {host}:{port}")
        return True
    except Exception as e:
        print(f"  {FAIL} Tor SOCKS5 at {host}:{port} – {e}")
        return False


def main():
    print("\n=== OSINT Framework – Setup Check ===\n")
    sections = [
        ("Python Version", check_python),
        ("Python Packages", check_packages),
        ("API Keys", check_env_keys),
        ("CLI Tools", check_cli_tools),
        ("Neo4j Database", check_neo4j),
        ("Tor Proxy", check_tor),
    ]
    results = {}
    for name, fn in sections:
        print(f"\n[{name}]")
        results[name] = fn()

    print("\n=== Summary ===")
    for name, ok in results.items():
        print(f"  {'PASS' if ok else FAIL} {name}")
    print()


if __name__ == "__main__":
    main()
