from pathlib import Path
import os, datetime, html, re, json

import piexif

# ---------- CONFIG ----------
BASE_DIR = Path(r"F:\BirdFramer\best_crops")
PAGE_TITLE_LABEL = "Bird Frames by Label"
PAGE_TITLE_DATE = "Bird Frames by Date"
THUMB_MAX = 300
OUT_SPECIES = BASE_DIR / "index.html"
OUT_DATES = BASE_DIR / "by_date.html"
LABEL_CHOICES = [
    "unprocessed",
    "cardinal", "bluejay", "woodpecker", "finch",
    "sparrow", "chickadee", "titmouse", "nuthatch",
    "mourning_dove", "starling", "grackle", "cat", "squirrel",
    "other-bird", "other animal", "no-animal", "reject image"
]
# ----------------------------

def parse_date_from_filename(name: str):
    """Extract YYYY-MM-DD from filenames like Backyard-0-20251005174033-20251005174113.mp4"""
    m = re.search(r"(\d{8})\d{6}", name)
    if not m:
        return "unknown"
    ds = m.group(1)
    return f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}"

def extract_label(img_path: Path):
    """Read label:* value from EXIF ImageDescription if present."""
    try:
        exif_dict = piexif.load(str(img_path))
        raw = exif_dict["0th"].get(piexif.ImageIFD.ImageDescription)
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        raw = raw.strip()
        if raw.lower().startswith("label:"):
            raw = raw[6:]
        return raw or None
    except Exception:
        return None


def label_key(label: str | None) -> str:
    if not label:
        return "unlabeled"
    cleaned = label.strip().lower()
    cleaned = cleaned.replace("_", " ").replace("-", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "unlabeled"


def label_display(label: str | None) -> str:
    """Return a human-friendly label string for headings."""
    if not label:
        return "Unlabeled"
    text = label.replace("_", " ").replace("-", " ")
    words = [w.capitalize() for w in text.strip().split() if w]
    return " ".join(words) if words else "Unlabeled"


def collect_images(base_dir):
    """Collect image metadata, including label, parent folder, and derived video name."""
    items: list[dict] = []
    for img in base_dir.rglob("*.jpg"):
        rel_path = os.path.relpath(img, base_dir).replace("\\", "/")
        relative_parts = Path(rel_path)
        parent = relative_parts.parent.name if relative_parts.parent.name else base_dir.name
        filename = relative_parts.name
        video_id = filename.split("_f")[0]
        date = parse_date_from_filename(video_id)
        raw_label = extract_label(img)
        items.append({
            "rel": rel_path,
            "parent": parent,
            "filename": filename,
            "video": video_id,
            "date": date,
            "label_raw": raw_label,
            "label_key": label_key(raw_label),
            "label_display": label_display(raw_label),
        })
    items.sort(key=lambda item: (item["label_key"], item["date"], item["rel"]))
    return items


def render_card(item: dict, interactive: bool) -> str:
    rel = item["rel"]
    current_label = item["label_raw"] or ""
    label_present = bool(item["label_raw"])
    label_text = label_display(item["label_raw"] if label_present else "unlabeled")
    label_tag_text = label_text if label_present else "Not labeled"
    label_tag_class = "" if label_present else "missing"
    video_text = item["video"]
    parent_text = item["parent"]

    meta_html = (
        f"<div class=\"meta\">"
        f"<div class=\"species\">Video: {html.escape(video_text)}</div>"
        f"<div class=\"folder\">Folder: {html.escape(parent_text)}</div>"
        "</div>"
    )

    if interactive:
        return f"""<div class=\"card\" data-rel=\"{html.escape(rel, quote=True)}\" data-current-label=\"{html.escape(current_label, quote=True)}\">
<a class=\"preview\" href=\"{html.escape(rel, quote=True)}\" target=\"_blank\" rel=\"noopener\">
  <img src=\"{html.escape(rel, quote=True)}\" width=\"{THUMB_MAX}\" loading=\"lazy\">
</a>
{meta_html}
<div class=\"label-tag\">Label: <span class=\"{label_tag_class}\">{html.escape(label_tag_text)}</span></div>
<div class=\"actions\"></div>
<div class=\"status\" aria-live=\"polite\"></div>
</div>"""
    return f"""<div class=\"card\">
<a href=\"{html.escape(rel, quote=True)}\"><img src=\"{html.escape(rel, quote=True)}\" width=\"{THUMB_MAX}\" loading=\"lazy\"></a>
{meta_html}
<div class=\"label-tag\">Label: <span class=\"{label_tag_class}\">{html.escape(label_tag_text)}</span></div>
</div>"""

def make_page(title, blocks, out_file, interactive=False):
    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    base_styles = """
body { background:#fafafa; font-family:sans-serif; margin:2em; }
h1 { text-align:center; }
.grid { display:flex; flex-wrap:wrap; gap:1em; justify-content:center; }
.card { display:flex; flex-direction:column; align-items:center; }
.card img { border-radius:8px; box-shadow:0 0 4px #999; }
details { margin:1.2em 0; border:1px solid #ddd; border-radius:8px; background:white; padding:0.5em 1em; }
summary { font-size:1.2em; font-weight:bold; cursor:pointer; outline:none; }
summary::marker { color:#555; }
.date-panel summary { position:sticky; top:0; display:block; background:#fafafa; padding:0.5em 0; border-bottom:1px solid #ddd; z-index:5; }
    .label-tag { margin-top:0.4em; font-size:0.78em; color:#555; text-align:center; }
    .label-tag .missing { color:#b14444; font-weight:600; }
"""
    if interactive:
        base_styles += """
.card { background:white; border:1px solid #e0e0e0; border-radius:12px; padding:1em; box-shadow:0 4px 10px rgba(0,0,0,0.08); transition:opacity 0.2s ease; max-width:320px; }
.card .meta { margin-top:0.4em; text-align:center; }
.card .meta .species { font-weight:600; color:#333; }
.card .meta .folder { font-size:0.8em; color:#777; }
.card a.preview { display:block; }
.card a.preview img { transition:transform 0.2s ease; }
.card a.preview:hover img { transform:scale(1.02); }
.actions { display:flex; flex-wrap:wrap; gap:0.4em; justify-content:center; margin-top:0.6em; }
.actions button { border:1px solid #cfcfcf; background:white; border-radius:999px; padding:0.35em 0.8em; font-size:0.82em; cursor:pointer; text-transform:capitalize; transition:all 0.15s ease; }
.actions button:hover { border-color:#999; background:#f3f3f3; }
.actions button:disabled { opacity:0.4; cursor:default; }
.actions button.active { background:#1f7a39; border-color:#1f7a39; color:#fff; }
.status { min-height:1.2em; margin-top:0.5em; font-size:0.78em; text-align:center; color:#666; }
.status.pending { color:#555; }
.status.ok { color:#1f7a39; }
.status.err { color:#c0392b; }
.card.working { opacity:0.75; }
.card.sorted { opacity:0.45; }
"""

    head = f"""<!DOCTYPE html><html lang=\"en\"><head>
<meta charset=\"UTF-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
<title>{html.escape(title)}</title>
<style>
{base_styles}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p style=\"text-align:center;color:#666;\">Generated {date}</p>
<div style=\"text-align:center;margin:1em 0;\">
    <a href=\"index.html\" style=\"margin:0 1em;\">View by Label</a> |
    <a href=\"by_date.html\" style=\"margin:0 1em;\">View by Date</a>
</div>
"""

    page = head + "\n".join(blocks)

    if interactive:
        labels_json = json.dumps(LABEL_CHOICES)
        script_lines = [
            "<script>",
            f"const LABEL_CHOICES = {labels_json};",
            "const MOVE_ENDPOINT = \"/move\";",
            "",
            "function labelCaption(label) {",
            "  return label.replace(/[-_]/g, ' ').replace(/\\b\\w/g, function (char) { return char.toUpperCase(); });",
            "}",
            "",
            "function setStatus(statusEl, state, message) {",
            "  statusEl.className = 'status ' + state;",
            "  statusEl.textContent = message;",
            "}",
            "",
            "function toggleButtons(buttons, disabled) {",
            "  buttons.forEach(function (btn) { btn.disabled = disabled; });",
            "}",
            "",
            "async function handleLabel(card, rel, label) {",
            "  const status = card.querySelector('.status');",
            "  const buttons = Array.from(card.querySelectorAll('.actions button'));",
            "  setStatus(status, 'pending', 'Moving to \"' + label + '\"...');",
            "  card.classList.add('working');",
            "  toggleButtons(buttons, true);",
            "  try {",
            "    const response = await fetch(MOVE_ENDPOINT, {",
            "      method: 'POST',",
            "      headers: { 'Content-Type': 'application/json' },",
            "      body: JSON.stringify({ src: rel, label: label })",
            "    });",
            "    const text = await response.text();",
            "    let payload = {};",
            "    try {",
            "      payload = text ? JSON.parse(text) : {};",
            "    } catch (err) {",
            "      payload = { error: text };",
            "    }",
            "    if (!response.ok || payload.error) {",
            "      throw new Error(payload.error || response.statusText);",
            "    }",
            "    setStatus(status, 'ok', 'Moved to \"' + label + '\"');",
            "    card.classList.remove('working');",
            "    card.classList.add('sorted');",
            "    setTimeout(function () {",
            "      card.remove();",
            "    }, 600);",
            "  } catch (err) {",
            "    console.error('Label move failed', err);",
            "    setStatus(status, 'err', err.message || 'Request failed');",
            "    card.classList.remove('working');",
            "    toggleButtons(buttons, false);",
            "  }",
            "}",
            "",
            "function buildButtons(card) {",
            "  const actions = card.querySelector('.actions');",
            "  if (!actions) { return; }",
            "  const rel = card.getAttribute('data-rel');",
            "  const current = (card.dataset.currentLabel || '').trim();",
            "  LABEL_CHOICES.forEach(function (label) {",
            "    const button = document.createElement('button');",
            "    button.type = 'button';",
            "    button.textContent = labelCaption(label);",
            "    button.dataset.label = label;",
            "    if (current && current.toLowerCase() === label.toLowerCase()) {",
            "      button.classList.add('active');",
            "    }",
            "    button.addEventListener('click', function () {",
            "      handleLabel(card, rel, label);",
            "    });",
            "    actions.appendChild(button);",
            "  });",
            "}",
            "",
            "document.addEventListener('DOMContentLoaded', function () {",
            "  document.querySelectorAll('.card[data-rel]').forEach(function (card) {",
            "    buildButtons(card);",
            "  });",
            "});",
            "</script>"
        ]
        page += "\n" + "\n".join(script_lines)

    page += "</body></html>"
    Path(out_file).write_text(page, encoding="utf-8")
    print(f"[ok] Gallery written to: {out_file}")

def build_label_gallery(images: list[dict]):
    label_groups: dict[str, list[dict]] = {}
    for item in images:
        label_groups.setdefault(item["label_key"], []).append(item)

    blocks: list[str] = []
    for label_key_value in sorted(label_groups.keys()):
        group_items = sorted(label_groups[label_key_value], key=lambda x: (x["video"], x["rel"]))
        display_name = label_display(group_items[0]["label_raw"])
        cards = "\n".join(render_card(item, interactive=True) for item in group_items)
        block = f"""<details open>
<summary>{html.escape(display_name)} ({len(group_items)})</summary>
<div class="grid">{cards}</div></details>"""
        blocks.append(block)

    make_page(PAGE_TITLE_LABEL, blocks, OUT_SPECIES, interactive=True)

def build_date_gallery(images: list[dict]):
    date_groups: dict[str, list[dict]] = {}
    unknown: list[dict] = []
    for item in images:
        if item["date"] == "unknown":
            unknown.append(item)
        else:
            date_groups.setdefault(item["date"], []).append(item)

    blocks: list[str] = []
    for date_value in sorted(date_groups.keys(), reverse=True):
        group_items = sorted(date_groups[date_value], key=lambda x: (x["label_key"], x["rel"]))
        cards = "\n".join(render_card(item, interactive=False) for item in group_items)
        block = f"""<details class="date-panel" open>
<summary>{html.escape(date_value)} ({len(group_items)} frames)</summary>
<div class="grid">{cards}</div></details>"""
        blocks.append(block)

    if unknown:
        cards = "\n".join(render_card(item, interactive=False) for item in unknown)
        block = f"""<details class="date-panel" open>
<summary>Unknown ({len(unknown)} frames)</summary>
<div class="grid">{cards}</div></details>"""
        blocks.append(block)

    make_page(PAGE_TITLE_DATE, blocks, OUT_DATES)

def main():
    images = collect_images(BASE_DIR)
    if not images:
        print(f"[info] No images found in {BASE_DIR}")
        return
    unique_labels = len({item["label_key"] for item in images})
    print(f"Found {len(images)} images across {unique_labels} labels.")
    build_label_gallery(images)
    build_date_gallery(images)

if __name__ == "__main__":
    main()
