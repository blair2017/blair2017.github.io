#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

import yaml
from bs4 import BeautifulSoup
from markdown import markdown


FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.S)


@dataclass(frozen=True)
class PostSource:
    path: Path
    front_matter: str
    body_markdown: str
    meta: dict[str, Any]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_front_matter(text: str) -> tuple[str, str, dict[str, Any]] | None:
    match = FRONT_MATTER_RE.match(text.replace("\r\n", "\n"))
    if not match:
        return None

    fm = match.group(1)
    body = match.group(2)
    meta = yaml.safe_load(fm) or {}
    if not isinstance(meta, dict):
        meta = {}
    return fm, body, meta


def find_candidate_posts(repo: Path) -> list[Path]:
    candidates: list[Path] = []

    posts_dir = repo / "_posts"
    if posts_dir.exists():
        for path in posts_dir.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".md", ".markdown"}:
                continue
            candidates.append(path)

    for path in repo.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".markdown"}:
            continue
        if re.match(r"^\d{4}-\d{2}-\d{2}-", path.name) is None:
            continue
        candidates.append(path)

    return sorted(set(candidates))


def load_site_config(repo: Path) -> dict[str, Any]:
    config_path = repo / "_config.yml"
    if not config_path.exists():
        return {}
    try:
        parsed = yaml.safe_load(read_text(config_path)) or {}
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def get_site_url(repo: Path, override: str | None) -> str:
    if override:
        return override.rstrip("/")
    config = load_site_config(repo)
    url = str(config.get("url") or "").strip()
    return url.rstrip("/")


def resolve_author_name(site_config: dict[str, Any], author_id: str | None) -> str | None:
    if not author_id:
        return None
    authors = site_config.get("authors")
    if isinstance(authors, dict):
        author_obj = authors.get(author_id)
        if isinstance(author_obj, dict):
            name = author_obj.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return author_id


def normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    s = str(value).strip()
    if not s:
        return None
    # Common Jekyll formats: "2015-12-15 16:49" or "2015-12-15 16:49:00 +0800"
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    return s


def ensure_layout(front_matter: str, desired_layout: str) -> str:
    lines = front_matter.split("\n")
    updated: list[str] = []
    layout_set = False
    for line in lines:
        if re.match(r"^\s*layout:\s*", line):
            if not layout_set:
                updated.append(f"layout: {desired_layout}")
                layout_set = True
            else:
                # Drop duplicate layout lines.
                continue
        else:
            updated.append(line)
    if not layout_set:
        updated.append(f"layout: {desired_layout}")
    return "\n".join(updated).rstrip("\n")


def maybe_update_post_layout(path: Path, desired_layout: str) -> bool:
    original = read_text(path)
    parsed = parse_front_matter(original)
    if not parsed:
        return False
    front_matter, body, meta = parsed

    current_layout = str(meta.get("layout") or "").strip()
    if current_layout not in {"post", desired_layout}:
        return False
    if current_layout == desired_layout:
        return False

    new_front_matter = ensure_layout(front_matter, desired_layout)
    updated = f"---\n{new_front_matter}\n---\n{body}"
    if updated == original.replace("\r\n", "\n"):
        return False
    write_text(path, updated)
    return True


def absolutize(url: str, site_url: str) -> str:
    if not site_url:
        return url
    u = url.strip()
    if not u:
        return u
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", u):
        return u
    if u.startswith("#"):
        return u
    if u.startswith("//"):
        return u
    base = site_url.rstrip("/") + "/"
    return urljoin(base, u.lstrip("/"))


def append_style(existing: str | None, addition: str) -> str:
    if not addition.strip():
        return existing or ""
    if not existing:
        return addition.strip().rstrip(";") + ";"
    merged = existing.strip()
    if not merged.endswith(";"):
        merged += ";"
    merged += " " + addition.strip().rstrip(";") + ";"
    return merged


def inline_styles(soup: BeautifulSoup, site_url: str) -> None:
    styles: dict[str, str] = {
        "p": "margin:0 0 16px; font-size:16px; line-height:1.85; color:#333; font-weight:400;",
        "h2": "margin:28px 0 14px; font-size:20px; line-height:1.45; padding-left:10px; border-left:4px solid #07c160; color:#111; font-weight:700;",
        "h3": "margin:24px 0 12px; font-size:18px; line-height:1.5; color:#111; font-weight:700;",
        "h4": "margin:18px 0 10px; font-size:16px; line-height:1.55; color:#111; font-weight:700;",
        "ul": "margin:0 0 16px; padding-left:22px;",
        "ol": "margin:0 0 16px; padding-left:22px;",
        "li": "margin-bottom:6px; line-height:1.9; color:#333; font-size:16px;",
        "blockquote": "margin:18px 0; padding:12px 14px; background:#f7f8fa; border-left:4px solid #07c160; color:#555;",
        "pre": "margin:16px 0; padding:12px 14px; background:#f7f8fa; border:1px solid #e8e8e8; border-radius:6px; overflow:auto; font-size:13px; line-height:1.6;",
        "a": "color:#576b95; text-decoration:none; border-bottom:1px solid rgba(87,107,149,0.25);",
        "strong": "font-weight:700; color:#111;",
        "img": "display:block; margin:18px auto; max-width:100%; border-radius:8px;",
        "table": "width:100%; border-collapse:collapse; margin:18px 0; font-size:14px;",
        "th": "border:1px solid #e8e8e8; padding:8px 10px; background:#f7f8fa; text-align:left;",
        "td": "border:1px solid #e8e8e8; padding:8px 10px; vertical-align:top;",
        "hr": "border:none; border-top:1px solid #eee; margin:24px 0;",
    }

    code_inline_style = (
        "background:#f2f4f5; padding:0 4px; border-radius:3px; font-size:13px; "
        'font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace;'
    )
    code_block_style = (
        "background:transparent; padding:0; border-radius:0; font-size:13px; "
        'font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace;'
    )

    # WeChat editors usually reserve H1 for the title. Downgrade body H1 to H2.
    for h1 in list(soup.find_all("h1")):
        h1.name = "h2"

    for tag_name, style in styles.items():
        for el in soup.find_all(tag_name):
            el["style"] = append_style(el.get("style"), style)

    for a in soup.find_all("a"):
        href = a.get("href")
        if isinstance(href, str):
            a["href"] = absolutize(href, site_url)

    for img in soup.find_all("img"):
        src = img.get("src")
        if isinstance(src, str):
            img["src"] = absolutize(src, site_url)

    for code in soup.find_all("code"):
        if code.parent and getattr(code.parent, "name", None) == "pre":
            code["style"] = append_style(code.get("style"), code_block_style)
        else:
            code["style"] = append_style(code.get("style"), code_inline_style)

    # Tighten blockquote internal paragraphs (avoid extra bottom margin).
    for bq in soup.find_all("blockquote"):
        for p in bq.find_all("p"):
            p["style"] = append_style(p.get("style"), "margin:0;")


def render_markdown_to_html(md: str) -> str:
    return markdown(
        md,
        extensions=[
            "extra",
            "fenced_code",
            "tables",
            "sane_lists",
        ],
        output_format="html5",
    )


def build_export_html(
    *,
    title: str,
    author: str | None,
    date: str | None,
    content_html: str,
    tags: list[str],
) -> str:
    safe_title = title.strip() or "Untitled"
    meta_parts = [p for p in [author, date] if p]
    meta_text = " · ".join(meta_parts)

    tags_html = ""
    if tags:
        tags_html = "".join(
            f'<span style="display:inline-block; margin:0 8px 8px 0; padding:5px 10px; border-radius:999px; background:#f2f4f5; color:#576b95; font-size:13px;">#{t}</span>'
            for t in tags
        )

    meta_block = ""
    if meta_text:
        meta_block = (
            f'<p style="margin:0 0 22px; font-size:13px; color:#8c8c8c; line-height:1.6;">{meta_text}</p>'
        )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
</head>
<body style="margin:0; padding:0; background:#ffffff;">
  <article style="max-width:740px; margin:0 auto; padding:24px 18px; font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,PingFang SC,Hiragino Sans GB,Microsoft YaHei,Noto Sans CJK SC,sans-serif; color:#111;">
    <h1 style="margin:0 0 12px; font-size:26px; line-height:1.35; font-weight:800;">{safe_title}</h1>
    {meta_block}
    <section style="font-size:16px; line-height:1.85; color:#333;">
      {content_html}
    </section>
    <footer style="margin-top:26px; padding-top:14px; border-top:1px dashed #eee;">
      {tags_html}
    </footer>
  </article>
</body>
</html>
"""


def extract_tags(meta: dict[str, Any]) -> list[str]:
    tags_value: Any = meta.get("tags")
    if tags_value is None:
        tags_value = meta.get("tag")
    if tags_value is None:
        return []
    if isinstance(tags_value, str):
        tags = [tags_value]
    elif isinstance(tags_value, list):
        tags = [str(x) for x in tags_value if str(x).strip()]
    else:
        tags = [str(tags_value)]
    return [t.strip() for t in tags if t.strip()]


def load_posts(repo: Path) -> list[PostSource]:
    posts: list[PostSource] = []
    for path in find_candidate_posts(repo):
        parsed = parse_front_matter(read_text(path))
        if not parsed:
            continue
        fm, body, meta = parsed
        layout = str(meta.get("layout") or "").strip()
        if layout not in {"post", "post-wechat"}:
            continue
        if meta.get("hidden") is True:
            continue
        posts.append(PostSource(path=path, front_matter=fm, body_markdown=body, meta=meta))
    return posts


def generate_exports(*, repo: Path, out_dir: Path, site_url: str, desired_layout: str) -> list[Path]:
    site_config = load_site_config(repo)
    posts = load_posts(repo)

    changed_layout_files: list[Path] = []
    for post in posts:
        if maybe_update_post_layout(post.path, desired_layout):
            changed_layout_files.append(post.path)

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for post in posts:
        title = str(post.meta.get("title") or post.path.stem).strip()
        date = normalize_date(post.meta.get("date"))
        author_id = str(post.meta.get("author") or "").strip() or None
        author = resolve_author_name(site_config, author_id)
        tags = extract_tags(post.meta)

        body_html = render_markdown_to_html(post.body_markdown)
        soup = BeautifulSoup(body_html, "html.parser")
        inline_styles(soup, site_url)
        content_html = str(soup)

        export_html = build_export_html(
            title=title,
            author=author,
            date=date,
            content_html=content_html,
            tags=tags,
        )

        out_path = out_dir / f"{post.path.stem}.html"
        write_text(out_path, export_html)
        written.append(out_path)

    index_path = out_dir / "index.html"
    index_items = "\n".join(
        f'<li style="margin:0 0 10px;"><a style="color:#576b95; text-decoration:none; border-bottom:1px solid rgba(87,107,149,0.25);" href="{p.name}">{p.stem}</a></li>'
        for p in sorted(written)
        if p.name != "index.html"
    )
    index_html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WeChat Exports</title>
</head>
<body style="margin:0; padding:0; background:#ffffff;">
  <main style="max-width:820px; margin:0 auto; padding:24px 18px; font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,PingFang SC,Hiragino Sans GB,Microsoft YaHei,Noto Sans CJK SC,sans-serif;">
    <h1 style="margin:0 0 12px; font-size:22px; line-height:1.4; font-weight:800;">WeChat Exports</h1>
    <p style="margin:0 0 18px; color:#666; line-height:1.7; font-size:14px;">
      打开任意文章页面后，全选正文复制，粘贴到微信公众号编辑器即可（样式已尽量做成内联）。
    </p>
    <ul style="margin:0; padding:0 0 0 18px; list-style:disc;">
      {index_items}
    </ul>
  </main>
</body>
</html>
"""
    write_text(index_path, index_html)
    written.append(index_path)

    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync WeChat-style branch content and export copy-ready HTML.")
    parser.add_argument("--repo", default=".", help="Repository root (default: .)")
    parser.add_argument("--out", default="wechat_exports", help="Output directory for exports (default: wechat_exports)")
    parser.add_argument("--site-url", default=None, help="Override site URL for absolutizing /assets/... links")
    parser.add_argument("--layout", default="post-wechat", help="Layout name to enforce for posts (default: post-wechat)")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    out_dir = (repo / args.out).resolve()
    site_url = get_site_url(repo, args.site_url)

    if not repo.exists():
        raise SystemExit(f"repo not found: {repo}")

    written = generate_exports(
        repo=repo,
        out_dir=out_dir,
        site_url=site_url,
        desired_layout=args.layout,
    )

    print(f"Wrote {len(written)} files to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

