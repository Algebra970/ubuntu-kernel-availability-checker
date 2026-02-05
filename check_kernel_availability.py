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


def parse_dependencies(depends_str: str) -> List[str]:
    """
    Parse Depends field from package metadata

    Args:
        depends_str: Dependencies string (e.g., "pkg1 (>= 1.0), pkg2 | pkg3")

    Returns:
        List of package names (first alternative of each OR group)
    """
    deps = []

    # Split by comma to get individual dependency groups
    for group in depends_str.split(','):
        group = group.strip()
        # Take first alternative (before |)
        primary = group.split('|')[0].strip()
        # Remove version constraint
        primary = re.sub(r'\s*\([^)]*\)', '', primary).strip()
        if primary:
            deps.append(primary)

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
                                    verbose: bool = False) -> List[str]:
    """
    Check a list of dependencies and collect missing ones

    Args:
        packages: Dictionary of all packages
        deps_to_check: List of package names to check
        verbose: Print verbose output

    Returns:
        List of missing package names
    """
    missing = []

    for i, dep in enumerate(deps_to_check, 1):
        if verbose:
            print(f"{i}. Checking {dep}...", end=' ')

        all_available, dep_missing, dep_unavailable = check_dependencies_recursive(packages, dep)

        if all_available:
            if verbose:
                print(f"{Color.GREEN}✓{Color.END}")
        else:
            missing.extend(dep_missing)
            missing.extend(dep_unavailable)
            if verbose:
                print(f"{Color.RED}✗{Color.END}")
                if dep_missing:
                    print(f"   Missing: {', '.join(set(dep_missing))}")

    return missing


def check_dependencies_recursive(packages: Dict[str, Dict],
                                 package_name: str,
                                 visited: Set[str] = None,
                                 depth: int = 0) -> Tuple[bool, List[str], List[str]]:
    """
    Recursively check if a package and all its dependencies are available

    Args:
        packages: Dictionary of all packages
        package_name: Package to check
        visited: Set of already-visited packages (to avoid circular deps)
        depth: Current recursion depth

    Returns:
        Tuple of (all_available, missing_packages, unavailable_packages)
    """
    if visited is None:
        visited = set()

    # Avoid infinite loops on circular dependencies
    if package_name in visited:
        return True, [], []

    visited.add(package_name)

    # Check if package exists
    info = get_package_info(packages, package_name)
    if not info:
        return False, [package_name], []

    missing = []
    unavailable = []
    all_available = True

    # Check dependencies if they exist
    if 'Depends' in info:
        deps = parse_dependencies(info['Depends'])
        for dep in deps:
            dep_available, dep_missing, dep_unavailable = check_dependencies_recursive(
                packages, dep, visited.copy(), depth + 1
            )
            if not dep_available:
                all_available = False
                missing.extend(dep_missing)
                unavailable.extend(dep_unavailable)

    return all_available, missing, unavailable


def check_kernel_package(package: str = 'linux-generic',
                        ubuntu_version: Optional[str] = None,
                        verbose: bool = False,
                        recursive: bool = False,
                        components: Optional[List[str]] = None,
                        use_cache: bool = True) -> bool:
    """
    Main function to check kernel package and dependencies

    Args:
        package: Package to check (default: linux-generic)
        ubuntu_version: Ubuntu version to check (auto-detect if None)
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
    all_packages = {}
    package_sources = {}  # Track which component/pocket each package comes from

    download_count = 0

    for component in components:
        for pocket in pockets:
            packages_content = download_packages_file(ubuntu_version, pocket, component=component, use_cache=use_cache)
            if packages_content:
                pocket_packages = parse_packages_file(packages_content)
                # Merge packages
                for pkg_name, pkg_info in pocket_packages.items():
                    if pkg_name not in all_packages:
                        all_packages[pkg_name] = pkg_info
                        package_sources[pkg_name] = f"{component}/{pocket}"
                    else:
                        # Keep existing - first found is kept
                        pass
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
    print(f"{Color.CYAN}Checking package: {Color.BOLD}{package}{Color.END}")
    info = get_package_info(packages, package)

    if not info:
        print(f"{Color.RED}✗ Package '{package}' not found in repository!{Color.END}\n")
        return False

    version = info.get('Version', 'unknown')
    source = package_sources.get(package, 'unknown')
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

    # Check each dependency and all their sub-dependencies
    all_checked_deps = set(all_deps)  # Track all dependencies we've checked
    repo_missing_deps = check_and_collect_missing_deps(packages, all_deps, verbose)

    # If recursive flag is set, check all transitive dependencies
    if recursive:
        print(f"\n{Color.CYAN}Performing full recursive dependency check...{Color.END}\n")

        # Build a complete dependency tree
        def collect_all_deps(pkg_name: str, visited: Set[str] = None) -> Set[str]:
            if visited is None:
                visited = set()
            if pkg_name in visited:
                return set()
            visited.add(pkg_name)

            info = get_package_info(packages, pkg_name)
            if not info or 'Depends' not in info:
                return set()

            deps = parse_dependencies(info['Depends'])
            result = set(deps)
            for dep in deps:
                result.update(collect_all_deps(dep, visited.copy()))
            return result

        # Collect all transitive dependencies
        all_transitive_deps = collect_all_deps(package)
        all_checked_deps.update(all_transitive_deps)

        print(f"Found {len(all_transitive_deps)} total transitive dependencies\n")

        # Check each transitive dependency (exclude already-checked direct deps)
        transitive_only = [d for d in sorted(all_transitive_deps) if d not in all_deps]
        transitive_missing = check_and_collect_missing_deps(packages, transitive_only, verbose)
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
        for i, dep in enumerate(all_deps, 1):
            all_available, missing, unavailable = check_dependencies_recursive(packages, dep)
            if all_available:
                source = package_sources.get(dep, 'unknown')
                if source not in by_source:
                    by_source[source] = []
                by_source[source].append(dep)

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
        """
    )

    parser.add_argument(
        '--package', '-p',
        default='linux-generic',
        help='Package to check (default: linux-generic)'
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
    success = check_kernel_package(args.package, args.ubuntu_version, args.verbose, args.recursive, args.components, not args.no_cache)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
