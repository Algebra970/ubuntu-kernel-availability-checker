# Ubuntu Kernel Availability Checker

Verify Ubuntu kernel package availability directly from `archive.ubuntu.com` without requiring a local apt installation. Detects meta-package publishing issues where kernel meta-packages are released before their actual kernel packages.

## Problem

Ubuntu occasionally publishes kernel meta-packages (`linux-generic`, `linux-image-generic`, `linux-headers-generic`) before the actual versioned kernel packages they depend on are available in the repository. This causes fresh Ubuntu installations to fail with dependency resolution errors:

```
E: Unable to locate package linux-modules-6.8.0-100-generic
E: Package has no installation candidate
```

This tool detects these availability issues by querying the repository metadata directly.

## Features

- **Direct Repository Queries**: Downloads and parses package metadata from archive.ubuntu.com without using local apt tools
- **Full Component Support**: Checks all Ubuntu repository components (main, restricted, universe, multiverse)
- **Multi-Pocket Coverage**: Verifies packages across all repository pockets (main, security, updates)
- **Recursive Dependency Analysis**: Optional full recursive check of all transitive dependencies
- **Auto-Detection**: Automatically detects the Ubuntu version or accepts manual specification for cross-version checking
- **Flexible Filtering**: Select specific components to check
- **Detailed Output**: Shows which repository source (component/pocket) each package comes from
- **Pure Python**: No external dependencies beyond Python's standard library

## Requirements

- Python 3.6+
- Internet connection to archive.ubuntu.com
- No local apt installation required

## Installation

Clone the repository:

```bash
git clone https://github.com/yourusername/ubuntu-kernel-availability-checker.git
cd ubuntu-kernel-availability-checker
```

## Usage

### Basic Usage

Check kernel availability on the current Ubuntu version:

```bash
python3 check_kernel_availability.py
```

### Check Specific Package

```bash
python3 check_kernel_availability.py --package linux-image-generic
```

### Cross-Version Check

```bash
python3 check_kernel_availability.py --ubuntu-version focal
python3 check_kernel_availability.py -u jammy
```

### Recursive Dependency Check

Perform a full recursive check of all transitive dependencies:

```bash
python3 check_kernel_availability.py --recursive
python3 check_kernel_availability.py -r
```

### Filter Components

Check only specific repository components:

```bash
python3 check_kernel_availability.py --components main universe
python3 check_kernel_availability.py -c main restricted
```

### Verbose Output

Show detailed information about each dependency:

```bash
python3 check_kernel_availability.py --verbose
python3 check_kernel_availability.py -v
```

### Combine Options

```bash
# Full recursive check with verbose output
python3 check_kernel_availability.py --recursive --verbose

# Check universe packages on focal with short flags
python3 check_kernel_availability.py -r -v -u focal -c universe

# Check specific package across all components
python3 check_kernel_availability.py -p linux-image-generic --components main universe
```

## Output Examples

### Successful Check

```
======================================================================
Ubuntu Kernel Package Availability Checker
(Querying archive.ubuntu.com directly)
======================================================================

Detected Ubuntu version: noble

Downloading packages from repository...
  ✓ main         / main     -  6099 packages
  ✓ main         / security -  7505 packages
  ✓ main         / updates  -  8879 packages
  ✓ restricted   / main     -   492 packages
  ✓ restricted   / security - 13335 packages
  ✓ restricted   / updates  - 14168 packages
  ✓ universe     / main     - 64754 packages
  ✓ universe     / security -  4373 packages
  ✓ universe     / updates  -  7367 packages
  ✓ multiverse   / main     -  1154 packages
  ✓ multiverse   / security -   137 packages
  ✓ multiverse   / updates  -   156 packages
✓ Downloaded from 12 sources
✓ Total unique packages available: 93736

Checking package: linux-generic
✓ Package found
  Version: 6.8.0-31.31
  Source: main/main
  Architecture: amd64

Checking dependencies...
Found 2 direct dependencies

Summary:
  Total direct dependencies: 2
  Available: 2

======================================================================
✓ ALL CHECKS PASSED
  The kernel package and all dependencies are available.
```

### Failed Check (with Issues)

```
Summary:
  Total direct dependencies: 2
  Available: 2
  Missing from repository: 3

Packages Missing from Repository:
  ✗ linux-headers-6.8.0-100-generic
  ✗ linux-modules-6.8.0-100-generic
  ✗ linux-modules-extra-6.8.0-100-generic

======================================================================
✗ ISSUES DETECTED:
  The kernel package or its dependencies have availability problems.
  Fresh installations may fail!
```

## Use Cases

- **Mirror Administrators**: Verify repository mirror completeness before deployment
- **CI/CD Pipelines**: Validate package availability as part of build/deployment process
- **System Administrators**: Troubleshoot installation failures on customer systems
- **Release Engineering**: Detect meta-package publishing issues early in the release cycle
- **Offline Environments**: Check repository status without requiring apt installation

## How It Works

1. Detects the Ubuntu version from `/etc/os-release` or accepts a manual specification
2. Downloads the compressed `Packages.gz` metadata files from archive.ubuntu.com for:
   - All requested components (main, restricted, universe, multiverse)
   - All pockets (main, security, updates)
3. Parses the package metadata to build a database of available packages
4. Checks if the target package and its dependencies exist in the database
5. Optionally performs recursive checking to validate the entire dependency tree
6. Generates a detailed report showing which packages are missing or available

## Exit Codes

- `0`: All checks passed, all packages are available
- `1`: Issues detected, one or more packages are missing from the repository

## Command-Line Reference

```
usage: check_kernel_availability.py [-h] [-p PACKAGE] [-u UBUNTU_VERSION]
                                     [-c {main,restricted,universe,multiverse} ...]
                                     [-v] [-r]

Check Ubuntu kernel package availability by querying archive.ubuntu.com

optional arguments:
  -h, --help            show this help message and exit
  -p, --package PACKAGE
                        Package to check (default: linux-generic)
  -u, --ubuntu-version UBUNTU_VERSION
                        Ubuntu version codename (e.g., focal, jammy, noble)
  -c, --components {main,restricted,universe,multiverse} ...
                        Repository components to check (default: all)
  -v, --verbose         Enable verbose output
  -r, --recursive       Perform full recursive check of all transitive dependencies
```

## Supported Ubuntu Versions

The tool works with any Ubuntu version that has repositories on archive.ubuntu.com:
- focal (20.04 LTS)
- jammy (22.04 LTS)
- noble (24.04 LTS)
- And all other currently maintained and archived Ubuntu releases

## Limitations

- Requires internet connectivity to archive.ubuntu.com
- Only checks for package existence, not actual package installability on the system
- Does not validate package integrity or signatures
- Cannot check PPAs or third-party repositories

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## Author

Created to address the recurring issue of kernel meta-package availability problems in Ubuntu repositories.
