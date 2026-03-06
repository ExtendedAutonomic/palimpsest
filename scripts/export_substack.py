"""
Export a Palimpsest experimenter post for Substack.

Reads a post markdown file, strips frontmatter, converts Obsidian image
embeds to standard markdown, copies images to an export folder, and
outputs clean markdown ready to paste into Substack's editor.

Usage:
    python scripts/export_substack.py 1        # export post_0001.md
    python scripts/export_substack.py 2        # export post_0002.md
    python scripts/export_substack.py all      # export all posts

Images are copied to exports/post_NNNN/images/ numbered in order of
appearance. The markdown references them with standard syntax so you
can see where each image belongs when pasting into Substack.

Screenshot placeholders like [Screenshot: ...] are preserved as-is.
These are notes for images that haven't been added yet.
"""

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "logs" / "experimenter"
ATTACHMENTS_DIR = POSTS_DIR / "attachments"
EXPORTS_DIR = ROOT / "exports"

# Additional places to search for images (e.g. Obsidian vault attachments)
EXTRA_IMAGE_DIRS = [
    Path(r"D:\Vault\+\attachments"),
    Path(r"D:\Vault"),
]


def find_image(filename: str) -> Path | None:
    """Search for an image file in known locations."""
    # Check attachments dir first
    candidate = ATTACHMENTS_DIR / filename
    if candidate.exists():
        return candidate

    # Check extra dirs
    for d in EXTRA_IMAGE_DIRS:
        candidate = d / filename
        if candidate.exists():
            return candidate

    return None


def strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter from markdown."""
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            # Skip the closing --- and any blank lines after it
            rest = text[end + 3:].lstrip("\n")
            return rest
    return text


def export_post(post_num: int) -> None:
    """Export a single post."""
    post_file = POSTS_DIR / f"post_{post_num:04d}.md"
    if not post_file.exists():
        print(f"  Post not found: {post_file}")
        return

    text = post_file.read_text(encoding="utf-8")

    # Strip frontmatter
    text = strip_frontmatter(text)

    # Set up export directory
    export_dir = EXPORTS_DIR / f"post_{post_num:04d}"
    images_dir = export_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # Find all Obsidian image embeds: ![[filename|size]] or ![[filename]]
    pattern = r"!\[\[([^\]|]+?)(?:\|[^\]]*?)?\]\]"
    matches = list(re.finditer(pattern, text))

    missing = []
    image_num = 0

    for match in matches:
        filename = match.group(1).strip()
        source = find_image(filename)

        if source:
            image_num += 1
            # Preserve extension, add number prefix
            ext = source.suffix
            numbered_name = f"{image_num:02d}_{filename}"
            dest = images_dir / numbered_name
            shutil.copy2(source, dest)

            # Replace with standard markdown image
            # Use the figure caption from the line below if present
            replacement = f"![{filename}](images/{numbered_name})"
            text = text.replace(match.group(0), replacement)
        else:
            missing.append(filename)
            # Replace with a visible placeholder
            replacement = f"<!-- MISSING IMAGE: {filename} -->"
            text = text.replace(match.group(0), replacement)

    # Write exported markdown
    output_file = export_dir / f"post_{post_num:04d}.md"
    output_file.write_text(text, encoding="utf-8")

    # Check for SVGs (Substack doesn't support them)
    svgs = list(images_dir.glob("*.svg"))

    # Report
    print(f"  Exported to: {export_dir}")
    print(f"  Images copied: {image_num}")
    if missing:
        print(f"  Missing images ({len(missing)}):")
        for m in missing:
            print(f"    - {m}")
    else:
        print("  All images found.")
    if svgs:
        print(f"  SVG warning: Substack doesn't support SVG. Convert these to PNG:")
        for s in svgs:
            print(f"    - {s.name}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/export_substack.py <post_number|all>")
        sys.exit(1)

    arg = sys.argv[1]

    if arg == "all":
        posts = sorted(POSTS_DIR.glob("post_????.md"))
        if not posts:
            print("No posts found.")
            return
        for p in posts:
            num = int(p.stem.split("_")[1])
            print(f"\nExporting post {num}...")
            export_post(num)
    else:
        try:
            num = int(arg)
        except ValueError:
            print(f"Invalid argument: {arg}")
            sys.exit(1)
        print(f"\nExporting post {num}...")
        export_post(num)

    print("\nDone. Paste the markdown into Substack's editor, then insert")
    print("images at each ![...] reference. Images are in the images/ folder,")
    print("numbered in order of appearance.")


if __name__ == "__main__":
    main()
