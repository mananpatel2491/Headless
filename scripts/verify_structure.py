import sys
import argparse
from pathlib import Path

def find_project_root(anchor_file="Project_Structure.md"):
    """Traverse upwards from the script location to find the project root."""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / anchor_file).exists():
            return parent
    return None

def get_logged_files(structure_file_path):
    """Extract file names from the Changelog table in the Markdown file."""
    logged_files = set()
    in_changelog = False
    
    with open(structure_file_path, "r", encoding="utf-8") as f:
        for line in f:
            if "## Changelog" in line:
                in_changelog = True
                continue
            
            if in_changelog and "|" in line:
                parts = line.split("|")
                if len(parts) >= 4:
                    # Column index 3 is 'Files Affected'
                    files_raw = parts[3].strip()
                    # Split by comma, remove backticks, and normalize paths
                    for file_entry in files_raw.split(","):
                        clean_name = file_entry.strip().replace("`", "")
                        # Standardize logic to skip headers and separators
                        if clean_name and not any(x in clean_name for x in ["Files Affected", "---", "Action", "Date"]):
                            # Normalize to posix path for consistent comparison
                            normalized_path = str(Path(clean_name.strip('/')).as_posix())
                            logged_files.add(normalized_path)
                            
    return logged_files

def verify():
    root = find_project_root()
    if not root:
        print("CRITICAL: Could not find Project_Structure.md in any parent directory.")
        sys.exit(1)

    structure_file = root / "Project_Structure.md"
    logged_files = get_logged_files(structure_file)

    # Scan for actual files, excluding .git and the structure file itself
    actual_files = []
    for path in root.rglob("*"):
        if path.is_file():
            # Relative path from root
            rel_path = path.relative_to(root)
            # Ignore .git directory and the manifest itself
            # Headless-specific exclusions: the virtualenv, runtime preview artifacts, test
            # caches, and OS metadata are never logged in the changelog.
            if ".git" in rel_path.parts or rel_path.name == "Project_Structure.md" or "__pycache__" in rel_path.parts or rel_path.name == ".env" or "bootstrap_prompts" in rel_path.parts or "docs" in rel_path.parts:
                continue
            if rel_path.parts[0] in (".venv", "venv", "previews", ".pytest_cache", "chrome-profile") or rel_path.name == ".DS_Store":
                continue
            # Spec Kit toolkit payload and its per-feature artifacts are mapped at
            # directory level in Project_Structure.md, not file-by-file
            if rel_path.parts[0] in (".specify", ".claude", ".gemini", "specs"):
                continue
            actual_files.append(str(rel_path.as_posix()))

    missing = [f for f in actual_files if str(f) not in logged_files]

    if missing:
        print(f"\033[91mCRITICAL: The following {len(missing)} files are missing from Project_Structure.md:\033[0m")
        for f in sorted(missing):
            print(f" - {f}")
        sys.exit(1)

    print("\033[92mSUCCESS: All files are accounted for in the changelog.\033[0m")
    sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify that all project files are logged in Project_Structure.md.")
    parser.add_argument("--model", type=str, help="Not used by this script (included for fleet consistency).")
    parser.add_argument("--dry-run", action="store_true", help="Included for fleet consistency; this script is read-only.")
    
    args = parser.parse_args()
    if args.dry_run:
        print("[DRY RUN] Verification mode active (read-only).")
    verify()