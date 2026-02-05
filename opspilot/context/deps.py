"""Dependency file parsing for multiple languages and package managers."""

import json
import re
from pathlib import Path
from typing import List, Dict, Optional


def read_dependencies(project_root: str) -> List[str]:
    """
    Read and parse dependencies from various package manager files.

    Supports:
    - Python: requirements.txt, Pipfile, pyproject.toml
    - Node.js: package.json
    - Ruby: Gemfile
    - Go: go.mod
    - Rust: Cargo.toml
    - Java: pom.xml, build.gradle

    Args:
        project_root: Root directory of the project

    Returns:
        List of dependency strings with versions where available
    """
    root = Path(project_root)
    dependencies = []

    # Python - requirements.txt
    if (root / "requirements.txt").exists():
        deps = parse_requirements_txt(root / "requirements.txt")
        dependencies.extend([f"[python] {d}" for d in deps])

    # Python - Pipfile
    if (root / "Pipfile").exists():
        deps = parse_pipfile(root / "Pipfile")
        dependencies.extend([f"[python] {d}" for d in deps])

    # Python - pyproject.toml
    if (root / "pyproject.toml").exists():
        deps = parse_pyproject_toml(root / "pyproject.toml")
        dependencies.extend([f"[python] {d}" for d in deps])

    # Node.js - package.json
    if (root / "package.json").exists():
        deps = parse_package_json(root / "package.json")
        dependencies.extend([f"[node] {d}" for d in deps])

    # Ruby - Gemfile
    if (root / "Gemfile").exists():
        deps = parse_gemfile(root / "Gemfile")
        dependencies.extend([f"[ruby] {d}" for d in deps])

    # Go - go.mod
    if (root / "go.mod").exists():
        deps = parse_go_mod(root / "go.mod")
        dependencies.extend([f"[go] {d}" for d in deps])

    # Rust - Cargo.toml
    if (root / "Cargo.toml").exists():
        deps = parse_cargo_toml(root / "Cargo.toml")
        dependencies.extend([f"[rust] {d}" for d in deps])

    # Java - pom.xml
    if (root / "pom.xml").exists():
        deps = parse_pom_xml(root / "pom.xml")
        dependencies.extend([f"[java] {d}" for d in deps])

    # Java - build.gradle
    for gradle_file in ["build.gradle", "build.gradle.kts"]:
        if (root / gradle_file).exists():
            deps = parse_build_gradle(root / gradle_file)
            dependencies.extend([f"[java] {d}" for d in deps])
            break

    return dependencies


def parse_requirements_txt(file_path: Path) -> List[str]:
    """Parse Python requirements.txt file."""
    try:
        content = file_path.read_text(errors='ignore')
        deps = []
        for line in content.splitlines():
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#') or line.startswith('-'):
                continue
            # Handle git+, http+ URLs
            if line.startswith(('git+', 'http+', 'https+')):
                # Extract package name from URL
                match = re.search(r'egg=([a-zA-Z0-9_-]+)', line)
                if match:
                    deps.append(match.group(1))
                continue
            # Standard requirement line: package==version or package>=version
            match = re.match(r'^([a-zA-Z0-9_-]+)', line)
            if match:
                deps.append(line)
        return deps
    except Exception:
        return []


def parse_pipfile(file_path: Path) -> List[str]:
    """Parse Python Pipfile."""
    try:
        content = file_path.read_text(errors='ignore')
        deps = []
        in_packages = False
        in_dev = False

        for line in content.splitlines():
            line = line.strip()
            if line == '[packages]':
                in_packages = True
                in_dev = False
            elif line == '[dev-packages]':
                in_packages = False
                in_dev = True
            elif line.startswith('['):
                in_packages = False
                in_dev = False
            elif (in_packages or in_dev) and '=' in line:
                # Extract package name
                parts = line.split('=', 1)
                if parts:
                    pkg_name = parts[0].strip().strip('"\'')
                    prefix = "(dev) " if in_dev else ""
                    deps.append(f"{prefix}{pkg_name}")
        return deps
    except Exception:
        return []


def parse_pyproject_toml(file_path: Path) -> List[str]:
    """Parse Python pyproject.toml file."""
    try:
        content = file_path.read_text(errors='ignore')
        deps = []

        # Simple regex-based parsing for dependencies
        # Look for dependencies = [...] or requires = [...]
        dep_pattern = r'(?:dependencies|requires)\s*=\s*\[(.*?)\]'
        matches = re.findall(dep_pattern, content, re.DOTALL)

        for match in matches:
            # Extract quoted strings
            quoted = re.findall(r'["\']([^"\']+)["\']', match)
            for dep in quoted:
                # Extract package name from requirement string
                pkg_match = re.match(r'^([a-zA-Z0-9_-]+)', dep)
                if pkg_match:
                    deps.append(dep)

        return deps
    except Exception:
        return []


def parse_package_json(file_path: Path) -> List[str]:
    """Parse Node.js package.json file."""
    try:
        content = file_path.read_text(errors='ignore')
        data = json.loads(content)
        deps = []

        # Regular dependencies
        if 'dependencies' in data:
            for name, version in data['dependencies'].items():
                deps.append(f"{name}@{version}")

        # Dev dependencies
        if 'devDependencies' in data:
            for name, version in data['devDependencies'].items():
                deps.append(f"(dev) {name}@{version}")

        # Peer dependencies
        if 'peerDependencies' in data:
            for name, version in data['peerDependencies'].items():
                deps.append(f"(peer) {name}@{version}")

        return deps
    except Exception:
        return []


def parse_gemfile(file_path: Path) -> List[str]:
    """Parse Ruby Gemfile."""
    try:
        content = file_path.read_text(errors='ignore')
        deps = []

        # Match gem 'name' or gem "name" with optional version
        pattern = r'gem\s+[\'"]([^\'"]+)[\'"](?:\s*,\s*[\'"]([^\'"]+)[\'"])?'
        matches = re.findall(pattern, content)

        for match in matches:
            name = match[0]
            version = match[1] if len(match) > 1 and match[1] else ""
            if version:
                deps.append(f"{name} ({version})")
            else:
                deps.append(name)

        return deps
    except Exception:
        return []


def parse_go_mod(file_path: Path) -> List[str]:
    """Parse Go go.mod file."""
    try:
        content = file_path.read_text(errors='ignore')
        deps = []

        # Match require statements
        # Single: require github.com/pkg/errors v0.9.1
        # Block: require (\n  github.com/pkg/errors v0.9.1\n)
        in_require_block = False

        for line in content.splitlines():
            line = line.strip()

            if line.startswith('require ('):
                in_require_block = True
                continue
            elif line == ')' and in_require_block:
                in_require_block = False
                continue

            if in_require_block or line.startswith('require '):
                # Extract module path and version
                line = line.replace('require ', '').strip()
                if line and not line.startswith('//'):
                    parts = line.split()
                    if len(parts) >= 2:
                        deps.append(f"{parts[0]}@{parts[1]}")
                    elif parts:
                        deps.append(parts[0])

        return deps
    except Exception:
        return []


def parse_cargo_toml(file_path: Path) -> List[str]:
    """Parse Rust Cargo.toml file."""
    try:
        content = file_path.read_text(errors='ignore')
        deps = []

        in_deps = False
        in_dev_deps = False

        for line in content.splitlines():
            line = line.strip()

            if line == '[dependencies]':
                in_deps = True
                in_dev_deps = False
            elif line == '[dev-dependencies]':
                in_deps = False
                in_dev_deps = True
            elif line.startswith('['):
                in_deps = False
                in_dev_deps = False
            elif (in_deps or in_dev_deps) and '=' in line:
                parts = line.split('=', 1)
                if parts:
                    name = parts[0].strip()
                    version = parts[1].strip().strip('"\'')
                    prefix = "(dev) " if in_dev_deps else ""
                    deps.append(f"{prefix}{name}@{version}")

        return deps
    except Exception:
        return []


def parse_pom_xml(file_path: Path) -> List[str]:
    """Parse Java pom.xml file (simple regex-based)."""
    try:
        content = file_path.read_text(errors='ignore')
        deps = []

        # Simple regex to extract dependencies
        # <dependency>
        #   <groupId>org.example</groupId>
        #   <artifactId>example</artifactId>
        #   <version>1.0.0</version>
        # </dependency>
        dep_pattern = r'<dependency>.*?<groupId>([^<]+)</groupId>.*?<artifactId>([^<]+)</artifactId>(?:.*?<version>([^<]+)</version>)?.*?</dependency>'
        matches = re.findall(dep_pattern, content, re.DOTALL)

        for match in matches:
            group_id = match[0]
            artifact_id = match[1]
            version = match[2] if len(match) > 2 and match[2] else "?"
            deps.append(f"{group_id}:{artifact_id}@{version}")

        return deps
    except Exception:
        return []


def parse_build_gradle(file_path: Path) -> List[str]:
    """Parse Java build.gradle file."""
    try:
        content = file_path.read_text(errors='ignore')
        deps = []

        # Match various dependency declarations
        # implementation 'group:artifact:version'
        # implementation "group:artifact:version"
        # compile 'group:artifact:version'
        # testImplementation 'group:artifact:version'
        pattern = r'(?:implementation|compile|testImplementation|testCompile|api|runtimeOnly)\s*[\'"]([^\'"]+)[\'"]'
        matches = re.findall(pattern, content)

        for match in matches:
            deps.append(match)

        return deps
    except Exception:
        return []


def get_project_type(project_root: str) -> Optional[str]:
    """
    Detect the primary project type based on dependency files.

    Returns: 'python', 'node', 'ruby', 'go', 'rust', 'java', or None
    """
    root = Path(project_root)

    if (root / "requirements.txt").exists() or (root / "Pipfile").exists() or (root / "pyproject.toml").exists():
        return "python"
    if (root / "package.json").exists():
        return "node"
    if (root / "Gemfile").exists():
        return "ruby"
    if (root / "go.mod").exists():
        return "go"
    if (root / "Cargo.toml").exists():
        return "rust"
    if (root / "pom.xml").exists() or (root / "build.gradle").exists():
        return "java"

    return None
