"""
Export a Palimpsest experimenter post for Substack.

Reads a post markdown file, strips frontmatter, converts Obsidian image
embeds, copies images to an export folder, and outputs both clean markdown
and a styled HTML file. Open the HTML in a browser, select all, copy,
and paste into Substack with formatting preserved.

Usage:
    python scripts/export_substack.py 1        # export post_0001.md
    python scripts/export_substack.py 2        # export post_0002.md
    python scripts/export_substack.py all      # export all posts

Requires: pip install markdown

Output:
    exports/post_NNNN/post_NNNN.md      Clean markdown
    exports/post_NNNN/post_NNNN.html    Open in browser → select all → copy → paste into Substack
    exports/post_NNNN/images/           Numbered images to drag into Substack
"""

import re
import shutil
import sys
from pathlib import Path

try:
    import markdown
except ImportError:
    print("Missing dependency. Install with: pip install markdown --break-system-packages")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "logs" / "experimenter"
ATTACHMENTS_DIR = POSTS_DIR / "attachments"
EXPORTS_DIR = ROOT / "exports"

# Additional places to search for images (e.g. Obsidian vault attachments)
EXTRA_IMAGE_DIRS = [
    Path(r"D:\Vault\+\attachments"),
    Path(r"D:\Vault"),
]

# Minimal styling so the HTML preview looks readable and images are
# visible, but the formatting pastes cleanly into Substack.
HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{
    max-width: 680px;
    margin: 2rem auto;
    padding: 0 1rem;
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 18px;
    line-height: 1.6;
    color: #1a1a1a;
  }}
  h1 {{ font-size: 2em; margin-top: 0; }}
  h2 {{ font-size: 1.4em; margin-top: 2em; }}
  blockquote {{
    border-left: 3px solid #ccc;
    margin: 1.2em 0;
    padding: 0.4em 1em;
    color: #444;
  }}
  blockquote p {{ margin: 0.4em 0; }}
  pre {{
    background: #f5f5f5;
    padding: 1em;
    overflow-x: auto;
    font-size: 0.85em;
    border-radius: 4px;
  }}
  code {{
    background: #f0f0f0;
    padding: 0.15em 0.3em;
    border-radius: 3px;
    font-size: 0.9em;
  }}
  pre code {{
    background: none;
    padding: 0;
  }}
  img {{
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1em 0;
  }}
  .figure-note {{
    font-style: italic;
    font-size: 0.9em;
    color: #666;
    margin-top: -0.5em;
    margin-bottom: 1.5em;
  }}
  .image-placeholder {{
    background: #fff3cd;
    border: 1px dashed #ffc107;
    padding: 0.8em 1em;
    margin: 1em 0;
    font-style: italic;
    color: #856404;
    border-radius: 4px;
  }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def find_image(filename: str) -> Path | None:
    """Search for an image file in known locations."""
    candidate = ATTACHMENTS_DIR / filename
    if candidate.exists():
        return candidate
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
            return text[end + 3:].lstrip("\n")
    return text


def convert_screenshot_placeholders(html: str) -> str:
    """Convert [Screenshot: ...] text into styled placeholders."""
    pattern = r'\[Screenshot: ([^\]]+)\]'
    replacement = r'<div class="image-placeholder">📷 Screenshot needed: \1</div>'
    return re.sub(pattern, replacement, html)


def convert_figure_notes(html: str) -> str:
    """Convert italic figure notes into styled divs."""
    # Match <p><em>Figure N: ...</em></p> patterns
    pattern = r'<p><em>(Figure \d+:.+?)</em></p>'
    replacement = r'<p class="figure-note">\1</p>'
    return re.sub(pattern, replacement, html)


def extract_title(text: str) -> str:
    """Extract the H1 title from markdown."""
    match = re.search(r'^# (.+)$', text, re.MULTILINE)
    return match.group(1) if match else "Palimpsest"


def export_post(post_num: int) -> None:
    """Export a single post."""
    post_file = POSTS_DIR / f"post_{post_num:04d}.md"
    if not post_file.exists():
        print(f"  Post not found: {post_file}")
        return

    text = post_file.read_text(encoding="utf-8")
    text = strip_frontmatter(text)

    # Set up export directory
    export_dir = EXPORTS_DIR / f"post_{post_num:04d}"
    images_dir = export_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # Find and replace Obsidian image embeds
    pattern = r"!\[\[([^\]|]+?)(?:\|[^\]]*?)?\]\]"
    matches = list(re.finditer(pattern, text))

    missing = []
    image_num = 0

    for match in matches:
        filename = match.group(1).strip()
        source = find_image(filename)

        if source:
            image_num += 1
            numbered_name = f"{image_num:02d}_{filename}"
            dest = images_dir / numbered_name
            shutil.copy2(source, dest)
            replacement = f"![{filename}](images/{numbered_name})"
            text = text.replace(match.group(0), replacement)
        else:
            missing.append(filename)
            replacement = f"<!-- MISSING IMAGE: {filename} -->"
            text = text.replace(match.group(0), replacement)

    # Extract title before conversion
    title = extract_title(text)

    # Write clean markdown
    md_file = export_dir / f"post_{post_num:04d}.md"
    md_file.write_text(text, encoding="utf-8")

    # Convert to HTML
    md_converter = markdown.Markdown(extensions=[
        'fenced_code',
        'tables',
    ])
    body_html = md_converter.convert(text)

    # Post-process HTML
    body_html = convert_screenshot_placeholders(body_html)
    body_html = convert_figure_notes(body_html)

    html = HTML_TEMPLATE.format(title=title, body=body_html)
    html_file = export_dir / f"post_{post_num:04d}.html"
    html_file.write_text(html, encoding="utf-8")

    # Check for SVGs
    svgs = list(images_dir.glob("*.svg"))

    # Report
    print(f"  Exported to: {export_dir}")
    print(f"  Markdown:    {md_file.name}")
    print(f"  HTML:        {html_file.name}  ← open in browser, select all, copy, paste into Substack")
    print(f"  Images:      {image_num} copied")
    if missing:
        print(f"  Missing images ({len(missing)}):")
        for m in missing:
            print(f"    - {m}")
    if svgs:
        print(f"  SVG warning: Substack doesn't support SVG. Convert to PNG:")
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

    print("\nWorkflow:")
    print("  1. Open the .html file in your browser")
    print("  2. Select all (Ctrl+A), copy (Ctrl+C)")
    print("  3. Paste into Substack's editor (Ctrl+V)")
    print("  4. Insert images from the images/ folder at each placeholder")
    print("  5. Preview and publish")


if __name__ == "__main__":
    main()
