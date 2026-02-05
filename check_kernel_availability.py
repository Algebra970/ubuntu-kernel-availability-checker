#!/usr/bin/env python3
"""
Ubuntu Kernel Package Availability Checker

This script checks if the latest linux-generic package and all its dependencies
are properly available in the Ubuntu repositories by querying archive.ubuntu.com directly.
It's designed to detect the issue where meta-packages are published before their
actual kernel packages.

Usage:
    python3 check_kernel_availability.py [--package PACKAGE] [--ubuntu-version VERSION] [--verbose]
"""

import urllib.request
import urllib.error
import gzip
import re
import argparse
import sys
import os
from typing import Dict, List, Set, Tuple, Optional
from pathlib import Path


class Color:
    """ANSI color codes for terminal output"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


SEPARATOR = '=' * 70


def get_cache_dir() -> Path:
    """
    Get or create the cache directory

    Returns:
        Path to the cache directory
    """
    cache_dir = Path.cwd() / 'cache'
    cache_dir.mkdir(exist_ok=True)
    return cache_dir


def build_package_url(ubuntu_version: str, pocket: str, component: str, arch: str = 'amd64') -> str:
    """
    Build the URL for a packages file

    Args:
        ubuntu_version: Ubuntu codename
        pocket: Repository pocket
        component: Repository component
        arch: Architecture (default: amd64)

    Returns:
        URL to the Packages.gz file
    """
    if pocket == 'main':
        return f"http://archive.ubuntu.com/ubuntu/dists/{ubuntu_version}/{component}/binary-{arch}/Packages.gz"
    return f"http://archive.ubuntu.com/ubuntu/dists/{ubuntu_version}-{pocket}/{component}/binary-{arch}/Packages.gz"


def get_cache_path(ubuntu_version: str, pocket: str, component: str) -> Path:
    """
    Get the cache file path for a packages file

    Args:
        ubuntu_version: Ubuntu codename
        pocket: Repository pocket
        component: Repository component

    Returns:
        Path to the cache file
    """
    cache_dir = get_cache_dir()
    filename = f"{ubuntu_version}_{pocket}_{component}.gz"
    return cache_dir / filename


def is_cache_current(ubuntu_version: str, pocket: str, component: str, arch: str = 'amd64') -> bool:
    """
    Check if cached file is still current by comparing with server's Last-Modified header

    Args:
        ubuntu_version: Ubuntu codename
        pocket: Repository pocket
        component: Repository component
        arch: Architecture (default: amd64)

    Returns:
        True if cache is current, False if stale or doesn't exist
    """
    cache_path = get_cache_path(ubuntu_version, pocket, component)
    if not cache_path.exists():
        return False

    url = build_package_url(ubuntu_version, pocket, component, arch)

    try:
        # Make HEAD request to get Last-Modified header
        req = urllib.request.Request(url, method='HEAD')
        with urllib.request.urlopen(req, timeout=10) as response:
            if 'Last-Modified' not in response.headers:
                # Can't determine freshness, assume cache is stale
                return False

            server_modified = response.headers['Last-Modified']
            # Parse Last-Modified header (e.g., "Wed, 21 Oct 2024 07:28:00 GMT")
            from email.utils import parsedate_to_datetime
            server_time = parsedate_to_datetime(server_modified).timestamp()
            cache_time = cache_path.stat().st_mtime
            return cache_time >= server_time
    except Exception:
        # If HEAD request fails, assume cache is current to avoid re-downloading
        return cache_path.exists()


def load_from_cache(ubuntu_version: str, pocket: str, component: str) -> Optional[str]:
    """
    Load decompressed packages data from cache if available and current

    Args:
        ubuntu_version: Ubuntu codename
        pocket: Repository pocket
        component: Repository component

    Returns:
        Decompressed Packages file content or None if not cached or stale
    """
    if not is_cache_current(ubuntu_version, pocket, component):
        return None

    cache_path = get_cache_path(ubuntu_version, pocket, component)
    if cache_path.exists():
        try:
            with gzip.open(cache_path, 'rb') as f:
                return f.read().decode('utf-8')
        except Exception:
            return None
    return None


def save_to_cache(ubuntu_version: str, pocket: str, component: str, content: str) -> None:
    """
    Save decompressed packages data to cache

    Args:
        ubuntu_version: Ubuntu codename
        pocket: Repository pocket
        component: Repository component
        content: Decompressed Packages file content
    """
    cache_path = get_cache_path(ubuntu_version, pocket, component)
    try:
        with gzip.open(cache_path, 'wb') as f:
            f.write(content.encode('utf-8'))
    except Exception:
        pass  # Silently fail if caching doesn't work


def detect_ubuntu_codename() -> Optional[str]:
    """
    Detect Ubuntu codename from system

    Returns:
        Ubuntu codename (e.g., 'focal', 'jammy') or None if not detected
    """
    # Try /etc/os-release first
    try:
        with open('/etc/os-release', 'r') as f:
            for line in f:
                if line.startswith('VERSION_CODENAME='):
                    codename = line.split('=')[1].strip().strip('"')
                    if codename:
                        return codename
    except (FileNotFoundError, IOError):
        pass

    # Try lsb_release file
    try:
        with open('/etc/lsb-release-codename', 'r') as f:
            codename = f.read().strip()
            if codename:
                return codename
    except (FileNotFoundError, IOError):
        pass

    return None


def download_packages_file(ubuntu_version: str, pocket: str = 'main',
                          arch: str = 'amd64',
                          component: str = 'main',
                          use_cache: bool = True) -> Optional[str]:
    """
    Download and decompress Packages file from Ubuntu repository with optional caching

    Args:
        ubuntu_version: Ubuntu codename (e.g., 'focal', 'jammy')
        pocket: Repository pocket ('main', 'security', 'updates')
        arch: Architecture (default: amd64)
        component: Repository component ('main', 'restricted', 'universe', 'multiverse')
        use_cache: Use cached data if available (default: True)

    Returns:
        Decompressed Packages file content or None if download fails
    """
    # Try cache first if enabled
    if use_cache:
        cached_content = load_from_cache(ubuntu_version, pocket, component)
        if cached_content:
            return cached_content

    url = build_package_url(ubuntu_version, pocket, component, arch)

    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            compressed_data = response.read()

        # Decompress gzip data
        decompressed = gzip.decompress(compressed_data).decode('utf-8')

        # Save to cache
        if use_cache:
            save_to_cache(ubuntu_version, pocket, component, decompressed)

        return decompressed
    except urllib.error.HTTPError as e:
        # Silently return None for 404 errors (component/pocket might not exist)
        if e.code == 404:
            return None
        print(f"{Color.RED}✗ HTTP Error {e.code} downloading {component}/{pocket}: {e.reason}{Color.END}")
        return None
    except urllib.error.URLError as e:
        print(f"{Color.RED}✗ Connection error downloading {component}/{pocket}: {e.reason}{Color.END}")
        return None
    except Exception as e:
        print(f"{Color.RED}✗ Error downloading {component}/{pocket}: {e}{Color.END}")
        return None


def _store_package(packages: Dict, package_info: Dict) -> None:
    """
    Store a parsed package entry in the packages dictionary

    Args:
        packages: Dictionary to store the package in
        package_info: Package metadata to store
    """
    if package_info and 'Package' in package_info:
        packages[package_info['Package']] = package_info


def parse_packages_file(content: str) -> Dict[str, Dict[str, any]]:
    """
    Parse Ubuntu Packages file content

    Args:
        content: Content of Packages file

    Returns:
        Dictionary mapping package names to their metadata
    """
    packages = {}
    current_package = {}

    for line in content.split('\n'):
        if line.strip() == '':
            # Empty line marks end of a package entry
            _store_package(packages, current_package)
            current_package = {}
        else:
            # Parse key-value pairs
            if ':' in line:
                key, value = line.split(':', 1)
                current_package[key.strip()] = value.strip()

    # Don't forget the last package
    _store_package(packages, current_package)
    return packages


def compare_versions(v1: str, v2: str) -> int:
    """
    Compare two Debian package versions

    Args:
        v1: First version string
        v2: Second version string

    Returns:
        -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2
    """
    # Simple comparison: split by '.' and compare numerically
    # For accurate Debian version comparison, would need dpkg.version
    # But this handles most cases like 6.8.0-31.31 vs 6.8.0-100.100
    parts1 = re.split(r'[-.]', v1)
    parts2 = re.split(r'[-.]', v2)

    for p1, p2 in zip(parts1, parts2):
        try:
            num1, num2 = int(p1), int(p2)
            if num1 < num2:
                return -1
            elif num1 > num2:
                return 1
        except ValueError:
            # Fallback to string comparison for non-numeric parts
            if p1 < p2:
                return -1
            elif p1 > p2:
                return 1

    # If all parts match, compare lengths
    if len(parts1) < len(parts2):
        return -1
    elif len(parts1) > len(parts2):
        return 1
    return 0


def parse_dependencies(depends_str: str) -> List[Tuple[str, Optional[str]]]:
    """
    Parse Depends field from package metadata with version constraints

    Args:
        depends_str: Dependencies string (e.g., "pkg1 (>= 1.0), pkg2 | pkg3")

    Returns:
        List of tuples (package_name, version_constraint) where version_constraint
        is the version requirement or None if no constraint
    """
    deps = []

    # Split by comma to get individual dependency groups
    for group in depends_str.split(','):
        group = group.strip()
        # Take first alternative (before |)
        primary = group.split('|')[0].strip()

        # Extract version constraint if present
        constraint_match = re.search(r'\s*\(([^)]*)\)', primary)
        version_constraint = None
        if constraint_match:
            version_constraint = constraint_match.group(1)

        # Extract package name (before the constraint)
        pkg_name = re.sub(r'\s*\([^)]*\)', '', primary).strip()
        if pkg_name:
            deps.append((pkg_name, version_constraint))

    return deps


def print_verdict(success: bool) -> None:
    """
    Print final verdict based on check result

    Args:
        success: Whether all checks passed
    """
    if success:
        print(f"{Color.GREEN}{Color.BOLD}✓ ALL CHECKS PASSED{Color.END}")
        print(f"{Color.GREEN}  The kernel package and all dependencies are available.{Color.END}")
    else:
        print(f"{Color.RED}{Color.BOLD}✗ ISSUES DETECTED:{Color.END}")
        print(f"{Color.RED}  The kernel package or its dependencies have availability problems.{Color.END}")
        print(f"{Color.RED}  Fresh installations may fail!{Color.END}")


def get_package_info(packages: Dict[str, Dict], name: str) -> Optional[Dict[str, any]]:
    """
    Get information about a specific package

    Args:
        packages: Dictionary of all packages from Packages file
        name: Package name to look up

    Returns:
        Package metadata dictionary or None if not found
    """
    return packages.get(name)


def check_and_collect_missing_deps(packages: Dict[str, Dict],
                                    deps_to_check: list,
                                    verbose: bool = False,
                                    latest_versions: Optional[Dict[str, str]] = None) -> List[str]:
    """
    Check a list of dependencies and collect missing ones

    Args:
        packages: Dictionary of all packages
        deps_to_check: List of tuples (package_name, version_constraint) to check
        verbose: Print verbose output
        latest_versions: Dictionary mapping package names to their latest versions

    Returns:
        List of missing package names
    """
    missing = []

    for i, (dep_name, constraint) in enumerate(deps_to_check, 1):
        if verbose:
            print(f"{i}. Checking {dep_name}...", end=' ')

        # Extract version from equality constraint if present
        requested_version = None
        if constraint and constraint.startswith('='):
            requested_version = constraint.split('=', 1)[1].strip()

        # Check if package exists with the required version
        dep_info = get_package_by_version(packages, dep_name, requested_version, latest_versions)
        if not dep_info:
            # Dependency not found with required version
            if requested_version:
                missing.append(f"{dep_name} (version {requested_version})")
            else:
                missing.append(dep_name)
            if verbose:
                print(f"{Color.RED}✗{Color.END}")
            continue

        if verbose:
            print(f"{Color.GREEN}✓{Color.END}")

        # Recursively check this dependency's dependencies with the requested version
        all_available, dep_missing, dep_unavailable = check_dependencies_recursive(
            packages, dep_name, requested_version, latest_versions=latest_versions
        )
        if not all_available:
            missing.extend(dep_missing)
            missing.extend(dep_unavailable)
            if verbose and dep_missing:
                print(f"   Missing: {', '.join(set(dep_missing))}")

    return missing


def check_dependencies_recursive(packages: Dict[str, Dict[str, Dict]],
                                 package_name: str,
                                 requested_version: Optional[str] = None,
                                 visited: Set[str] = None,
                                 depth: int = 0,
                                 latest_versions: Optional[Dict[str, str]] = None) -> Tuple[bool, List[str], List[str]]:
    """
    Recursively check if a package and all its dependencies are available

    Args:
        packages: Dictionary of all packages {name: {version: info}}
        package_name: Package to check
        requested_version: Specific version to check (None for latest)
        visited: Set of already-visited packages (to avoid circular deps)
        depth: Current recursion depth
        latest_versions: Dictionary mapping package names to their latest versions

    Returns:
        Tuple of (all_available, missing_packages, unavailable_packages)
    """
    if visited is None:
        visited = set()

    # Avoid infinite loops on circular dependencies
    if package_name in visited:
        return True, [], []

    visited.add(package_name)

    # Check if package exists with the requested version
    info = get_package_by_version(packages, package_name, requested_version, latest_versions)
    if not info:
        version_str = f" (version {requested_version})" if requested_version else ""
        return False, [f"{package_name}{version_str}"], []

    missing = []
    unavailable = []
    all_available = True

    # Check dependencies if they exist
    if 'Depends' in info:
        deps = parse_dependencies(info['Depends'])
        for dep_name, constraint in deps:
            # If there's an equality constraint, use that specific version
            dep_requested_version = None
            if constraint and constraint.startswith('='):
                # Extract version from constraint like "= 1.0" or "= 1.0-1"
                dep_requested_version = constraint.split('=', 1)[1].strip()

            # Recursively check this dependency with the version constraint
            dep_available, dep_missing, dep_unavailable = check_dependencies_recursive(
                packages, dep_name, dep_requested_version, visited.copy(), depth + 1, latest_versions
            )
            if not dep_available:
                all_available = False
                missing.extend(dep_missing)
                unavailable.extend(dep_unavailable)

    return all_available, missing, unavailable


def get_package_by_version(packages: Dict[str, Dict[str, Dict]], name: str, version: Optional[str] = None,
                           latest_versions: Optional[Dict[str, str]] = None) -> Optional[Dict]:
    """
    Get a specific version of a package or the latest if version is None

    Args:
        packages: Dictionary of all packages {name: {version: info}}
        name: Package name
        version: Specific version to find (None for latest)
        latest_versions: Dictionary mapping package names to their latest versions

    Returns:
        Package metadata or None if not found
    """
    if name not in packages:
        return None

    versions_dict = packages[name]
    if not versions_dict:
        return None

    if version is None:
        # Return the latest version if we have that info
        if latest_versions and name in latest_versions:
            latest_ver = latest_versions[name]
            return versions_dict.get(latest_ver)
        # Fallback: return any version (shouldn't happen in normal operation)
        return next(iter(versions_dict.values()))

    # Return specific version if it exists
    return versions_dict.get(version)


def check_kernel_package(package: str = 'linux-generic',
                        ubuntu_version: Optional[str] = None,
                        package_version: Optional[str] = None,
                        verbose: bool = False,
                        recursive: bool = False,
                        components: Optional[List[str]] = None,
                        use_cache: bool = True) -> bool:
    """
    Main function to check kernel package and dependencies

    Args:
        package: Package to check (default: linux-generic)
        ubuntu_version: Ubuntu version to check (auto-detect if None)
        package_version: Specific package version to check (None for latest)
        verbose: Print verbose output
        recursive: Check all transitive dependencies recursively
        components: List of components to check (default: all)
        use_cache: Use cached data if available (default: True)

    Returns:
        True if all checks pass, False otherwise
    """
    if components is None:
        components = ['main', 'restricted', 'universe', 'multiverse']

    print(f"{Color.BOLD}{SEPARATOR}{Color.END}")
    print(f"{Color.BOLD}Ubuntu Kernel Package Availability Checker{Color.END}")
    print(f"{Color.BOLD}(Querying archive.ubuntu.com directly){Color.END}")
    print(f"{Color.BOLD}{SEPARATOR}{Color.END}\n")

    # Detect Ubuntu version if not provided
    if not ubuntu_version:
        detected = detect_ubuntu_codename()
        if detected:
            ubuntu_version = detected
            print(f"{Color.CYAN}Detected Ubuntu version: {Color.BOLD}{ubuntu_version}{Color.END}\n")
        else:
            print(f"{Color.RED}✗ Could not detect Ubuntu version!{Color.END}")
            print(f"{Color.RED}Please specify with --ubuntu-version{Color.END}\n")
            return False
    else:
        print(f"{Color.CYAN}Using Ubuntu version: {Color.BOLD}{ubuntu_version}{Color.END}\n")

    # Download packages from all pockets and components
    print(f"{Color.CYAN}Downloading packages from repository...{Color.END}")
    pockets = ['main', 'security', 'updates']
    all_packages = {}  # {name: {version: info}}
    package_sources = {}  # {name: {version: source}}
    latest_versions = {}  # {name: latest_version}

    download_count = 0

    for component in components:
        for pocket in pockets:
            packages_content = download_packages_file(ubuntu_version, pocket, component=component, use_cache=use_cache)
            if packages_content:
                pocket_packages = parse_packages_file(packages_content)
                # Merge packages, storing all versions
                for pkg_name, pkg_info in pocket_packages.items():
                    version = pkg_info.get('Version', '')

                    # Initialize package if not seen before
                    if pkg_name not in all_packages:
                        all_packages[pkg_name] = {}
                        package_sources[pkg_name] = {}
                        latest_versions[pkg_name] = version

                    # Store this version if we haven't seen it
                    if version not in all_packages[pkg_name]:
                        all_packages[pkg_name][version] = pkg_info
                        package_sources[pkg_name][version] = f"{component}/{pocket}"

                        # Update latest version if this is newer
                        if compare_versions(latest_versions[pkg_name], version) < 0:
                            latest_versions[pkg_name] = version

                download_count += 1
                if not verbose:
                    print(f"  {Color.GREEN}✓{Color.END} {component:12} / {pocket:8} - {len(pocket_packages):5} packages")

    if not all_packages:
        print(f"{Color.RED}✗ Failed to download packages from any source!{Color.END}\n")
        return False

    print(f"{Color.GREEN}✓ Downloaded from {download_count} sources{Color.END}")
    print(f"{Color.GREEN}✓ Total unique packages available: {len(all_packages)}{Color.END}\n")

    # Parse packages
    packages = all_packages

    # Check main package
    if package_version:
        print(f"{Color.CYAN}Checking package: {Color.BOLD}{package}{Color.END} (version {package_version})")
    else:
        print(f"{Color.CYAN}Checking package: {Color.BOLD}{package}{Color.END} (latest)")

    info = get_package_by_version(packages, package, package_version, latest_versions)

    if not info:
        if package_version:
            print(f"{Color.RED}✗ Package '{package}' version '{package_version}' not found in repository!{Color.END}\n")
            # Show available versions
            pkg_info = get_package_info(packages, package)
            if pkg_info:
                print(f"{Color.YELLOW}Available version: {pkg_info.get('Version', 'unknown')}{Color.END}\n")
        else:
            print(f"{Color.RED}✗ Package '{package}' not found in repository!{Color.END}\n")
        return False

    version = info.get('Version', 'unknown')
    source = package_sources.get(package, {}).get(version, 'unknown')
    print(f"{Color.GREEN}✓ Package found{Color.END}")
    print(f"  Version: {Color.BOLD}{version}{Color.END}")
    print(f"  Source: {source}")
    print(f"  Architecture: {info.get('Architecture', 'unknown')}\n")

    # Check dependencies
    print(f"{Color.CYAN}Checking dependencies...{Color.END}")

    if 'Depends' not in info:
        print(f"{Color.YELLOW}No dependencies found{Color.END}\n")
        print(f"{Color.BOLD}{SEPARATOR}{Color.END}")
        print_verdict(True)
        return True

    all_deps = parse_dependencies(info['Depends'])
    print(f"Found {len(all_deps)} direct dependencies\n")

    # Extract just the package names for tracking
    all_deps_names = [name for name, _ in all_deps]

    # Check each dependency and all their sub-dependencies
    all_checked_deps = set(all_deps_names)  # Track all dependencies we've checked
    repo_missing_deps = check_and_collect_missing_deps(packages, all_deps, verbose, latest_versions)

    # If recursive flag is set, check all transitive dependencies
    if recursive:
        print(f"\n{Color.CYAN}Performing full recursive dependency check...{Color.END}\n")

        # Build a complete dependency tree
        def collect_all_deps(pkg_name: str, requested_version: Optional[str] = None, visited: Set[str] = None) -> Set[str]:
            if visited is None:
                visited = set()
            if pkg_name in visited:
                return set()
            visited.add(pkg_name)

            info = get_package_by_version(packages, pkg_name, requested_version, latest_versions)
            if not info or 'Depends' not in info:
                return set()

            deps = parse_dependencies(info['Depends'])
            result = set(dep_name for dep_name, _ in deps)
            for dep_name, constraint in deps:
                # Extract version from constraint if present
                dep_requested_version = None
                if constraint and constraint.startswith('='):
                    dep_requested_version = constraint.split('=', 1)[1].strip()
                result.update(collect_all_deps(dep_name, dep_requested_version, visited.copy()))
            return result

        # Collect all transitive dependencies with the requested version
        all_transitive_deps = collect_all_deps(package, package_version)
        all_checked_deps.update(all_transitive_deps)

        print(f"Found {len(all_transitive_deps)} total transitive dependencies\n")

        # Check each transitive dependency (exclude already-checked direct deps)
        transitive_only = [(d, None) for d in sorted(all_transitive_deps) if d not in all_deps_names]
        transitive_missing = check_and_collect_missing_deps(packages, transitive_only, verbose, latest_versions)
        repo_missing_deps.extend(transitive_missing)

    # Remove duplicates
    repo_missing_deps = list(set(repo_missing_deps))

    # Print summary
    available_count = len(all_deps) - len([d for d in all_deps if any(
        check_dependencies_recursive(packages, d)[1]
    )])

    print(f"\n{Color.BOLD}Summary:{Color.END}")
    if recursive:
        print(f"  Total dependencies checked: {len(all_checked_deps)}")
        print(f"  Direct dependencies: {len(all_deps)}")
        print(f"  Transitive dependencies: {len(all_checked_deps) - len(all_deps)}")
    else:
        print(f"  Total direct dependencies: {len(all_deps)}")

    available = len(all_checked_deps) - len(set(all_checked_deps) & set(repo_missing_deps))
    print(f"  {Color.GREEN}Available: {available}{Color.END}")

    if repo_missing_deps:
        print(f"  {Color.RED}Missing from repository: {len(set(repo_missing_deps))}{Color.END}")

    # Print packages missing from repository
    if repo_missing_deps:
        print(f"\n{Color.RED}{Color.BOLD}Packages Missing from Repository:{Color.END}")
        for dep in sorted(set(repo_missing_deps)):
            print(f"  {Color.RED}✗ {dep}{Color.END}")

    # Print available dependencies by source (in verbose mode)
    if verbose and not repo_missing_deps:
        print(f"\n{Color.CYAN}{Color.BOLD}Dependency Sources:{Color.END}")
        by_source = {}
        for i, (dep_name, constraint) in enumerate(all_deps, 1):
            # Extract version from constraint if present
            requested_version = None
            if constraint and constraint.startswith('='):
                requested_version = constraint.split('=', 1)[1].strip()

            all_available, missing, unavailable = check_dependencies_recursive(
                packages, dep_name, requested_version, latest_versions=latest_versions
            )
            if all_available:
                dep_versions = packages.get(dep_name, {})
                if dep_versions:
                    # Get the version we used
                    if requested_version:
                        dep_version = requested_version
                    elif dep_name in latest_versions:
                        dep_version = latest_versions[dep_name]
                    else:
                        dep_version = next(iter(dep_versions.keys()))

                    source = package_sources.get(dep_name, {}).get(dep_version, 'unknown')
                    if source not in by_source:
                        by_source[source] = []
                    by_source[source].append(dep_name)

        for source in sorted(by_source.keys()):
            print(f"  {source}: {len(by_source[source])} package(s)")

    # Final verdict
    print(f"\n{Color.BOLD}{SEPARATOR}{Color.END}")
    success = not bool(repo_missing_deps)
    print_verdict(success)
    return success


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Check Ubuntu kernel package availability by querying archive.ubuntu.com',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check linux-generic (auto-detects Ubuntu version, checks all components)
  python3 check_kernel_availability.py

  # Check a specific package
  python3 check_kernel_availability.py --package linux-image-generic

  # Check a specific package version
  python3 check_kernel_availability.py --package-version 6.8.0-31.31

  # Check against specific Ubuntu version
  python3 check_kernel_availability.py --ubuntu-version focal

  # Check only specific components
  python3 check_kernel_availability.py --components main universe

  # Full recursive check of all transitive dependencies
  python3 check_kernel_availability.py --recursive

  # Skip cache and download fresh data
  python3 check_kernel_availability.py --no-cache

  # Verbose output
  python3 check_kernel_availability.py --verbose

  # Combine multiple flags
  python3 check_kernel_availability.py -r -v --ubuntu-version jammy --components main restricted

  # Check specific package version with recursive dependencies
  python3 check_kernel_availability.py -pv 6.8.0-31.31 -r
        """
    )

    parser.add_argument(
        '--package', '-p',
        default='linux-generic',
        help='Package to check (default: linux-generic)'
    )

    parser.add_argument(
        '--package-version', '-pv',
        default=None,
        help='Specific package version to check (default: latest available)'
    )

    parser.add_argument(
        '--ubuntu-version', '-u',
        default=None,
        help='Ubuntu version codename (e.g., focal, jammy, noble). Auto-detects if not specified.'
    )

    parser.add_argument(
        '--components', '-c',
        nargs='+',
        default=['main', 'restricted', 'universe', 'multiverse'],
        choices=['main', 'restricted', 'universe', 'multiverse'],
        help='Repository components to check (default: all)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )

    parser.add_argument(
        '--recursive', '-r',
        action='store_true',
        help='Perform full recursive check of all transitive dependencies'
    )

    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='Skip cache and download fresh packages data from repository'
    )

    args = parser.parse_args()

    # Run the check
    success = check_kernel_package(
        args.package,
        args.ubuntu_version,
        args.package_version,
        args.verbose,
        args.recursive,
        args.components,
        not args.no_cache
    )

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
