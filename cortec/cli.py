"""
Cortec CLI — developer interface for memory management.
"""

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich import box
from rich.panel import Panel

from .config import CortecPaths, DEFAULT_PROJECT
from .storage.db import MetadataStore
from .storage.vector import VectorStore
from .security.scanner import scan
from .security.redactor import redact
from .ingest import summarize, archive_session

console = Console()
paths   = CortecPaths()


def _db() -> MetadataStore:
    paths.init()
    return MetadataStore(paths.db)

def _vector() -> VectorStore:
    paths.init()
    return VectorStore(paths.chroma)


# ── CLI group ─────────────────────────────────────────────────────────────────

@click.group()
@click.version_option(package_name="cortec-mcp")
def main():
    """Cortec — local-first memory for developer workflows."""


# ── cortec init ───────────────────────────────────────────────────────────────

@main.command()
@click.argument("project", default=DEFAULT_PROJECT)
def init(project: str):
    """Initialize Cortec storage for a project."""
    paths.init()
    cortec_md = Path.cwd() / ".cortec" / "CORTEC.md"
    cortec_md.parent.mkdir(parents=True, exist_ok=True)
    if not cortec_md.exists():
        cortec_md.write_text(
            f"# CORTEC.md\n\nproject: {project}\nauthor: Raj Kumar Satya\n\n"
            "## Notes\n- Add project-specific memory rules here.\n"
        )
        console.print(f"[green]Created[/] .cortec/CORTEC.md")
    console.print(f"[green]✓[/] Cortec initialized for project: [bold]{project}[/]")
    console.print(f"  Storage: {paths.base}")


# ── cortec remember ───────────────────────────────────────────────────────────

@main.command()
@click.argument("text")
@click.option("--project", "-p", default=DEFAULT_PROJECT, help="Project name.")
@click.option("--type",    "-t", default="general",       help="Memory type.")
@click.option("--source",  "-s", default="session",       help="Memory source.")
@click.option("--tags",    multiple=True,                  help="Tags (repeatable).")
@click.option("--auto",    is_flag=True,                   help="Store without approval prompt.")
def remember(text, project, type, source, tags, auto):
    """Store a memory. Prompts for approval by default."""
    clean = redact(text)
    result = scan(clean)
    if not result.clean:
        console.print(f"[red]✗ Secret scan failed:[/] {', '.join(result.findings)}")
        sys.exit(1)

    db = _db()
    vector = _vector()

    from .config import Confidence
    confidence = Confidence.from_source(source)

    if not auto:
        console.print(Panel(clean, title="Memory to store", border_style="yellow"))
        console.print(f"  Project:    [bold]{project}[/]")
        console.print(f"  Type:       [bold]{type}[/]")
        console.print(f"  Confidence: [bold]{confidence}[/]")
        if not click.confirm("Save this memory?"):
            console.print("[yellow]Cancelled.[/]")
            return

    memory_id = db.insert(
        summary=clean, project=project, type_=type,
        source=source, confidence=confidence,
        tags=list(tags), approved=True,
    )
    vector.add(memory_id, clean, {"project": project, "type": type, "source": source})
    console.print(f"[green]✓[/] Stored memory [bold]{memory_id}[/]  (confidence: {confidence})")


# ── cortec recall ─────────────────────────────────────────────────────────────

@main.command()
@click.argument("query")
@click.option("--project", "-p", default=None, help="Limit to a project.")
@click.option("--top",     "-n", default=5,    help="Number of results.")
def recall(query, project, top):
    """Retrieve memories matching a query."""
    db     = _db()
    vector = _vector()

    if vector.count() == 0:
        console.print("[yellow]No memories stored yet. Use 'cortec remember' first.[/]")
        return

    hits = vector.search(query, top_k=top, project=project)
    if not hits:
        console.print(f"[yellow]No results for:[/] {query}")
        return

    for hit in hits:
        meta = db.get(hit["id"])
        if not meta:
            continue
        console.print(
            Panel(
                hit["document"],
                title=f"[bold]{hit['id']}[/]  score={hit['score']}  confidence={meta['confidence']}",
                subtitle=f"source={meta['source']}  project={meta['project']}  {meta['created_at'][:10]}",
                border_style="cyan",
            )
        )


# ── cortec forget ─────────────────────────────────────────────────────────────

@main.command()
@click.argument("memory_id")
def forget(memory_id: str):
    """Permanently delete a memory by ID."""
    db     = _db()
    vector = _vector()
    if click.confirm(f"Delete memory {memory_id}? This cannot be undone."):
        deleted = db.delete(memory_id)
        vector.delete(memory_id)
        if deleted:
            console.print(f"[green]✓[/] Deleted memory [bold]{memory_id}[/]")
        else:
            console.print(f"[red]Memory {memory_id} not found.[/]")


# ── cortec approve ────────────────────────────────────────────────────────────

@main.command()
@click.argument("memory_id")
def approve(memory_id: str):
    """Approve a pending memory and index it."""
    db     = _db()
    vector = _vector()
    meta   = db.get(memory_id)
    if not meta:
        console.print(f"[red]Memory {memory_id} not found.[/]")
        return
    console.print(Panel(meta["summary"], title=f"Approve {memory_id}?", border_style="yellow"))
    if click.confirm("Approve and index?"):
        db.approve(memory_id)
        vector.add(memory_id, meta["summary"], {
            "project": meta["project"],
            "type":    meta["type"],
            "source":  meta["source"],
        })
        console.print(f"[green]✓[/] Memory [bold]{memory_id}[/] approved and indexed.")


# ── cortec status ─────────────────────────────────────────────────────────────

@main.command()
@click.option("--project", "-p", default=None, help="Filter by project.")
def status(project: str | None):
    """Show memory counts and pending approvals."""
    db     = _db()
    vector = _vector()
    counts = db.count(project=project)
    pending = db.list_pending(project=project)

    console.print(Panel(
        f"[bold]Total memories:[/]   {counts['total']}\n"
        f"[bold]Approved:[/]          {counts['approved']}\n"
        f"[bold]Pending approval:[/]  {counts['pending']}\n"
        f"[bold]Vector index:[/]      {vector.count()} entries\n"
        f"[bold]Storage path:[/]      {paths.base}",
        title="Cortec Status",
        border_style="green",
    ))

    if pending:
        console.print(f"\n[yellow]Pending memories ({len(pending)}):[/]")
        for m in pending:
            console.print(f"  [bold]{m['id']}[/]  {m['summary'][:60]}…")
        console.print("\nRun [bold]cortec approve <id>[/] to index a memory.")


# ── cortec export ─────────────────────────────────────────────────────────────

@main.command()
@click.option("--project", "-p", default=None,      help="Filter by project.")
@click.option("--out",     "-o", default="cortec_export.json", help="Output file.")
def export(project: str | None, out: str):
    """Export all memories to a JSON file."""
    db       = _db()
    memories = db.list_all(project=project, approved_only=False)
    out_path = Path(out)
    out_path.write_text(json.dumps(memories, indent=2))
    console.print(f"[green]✓[/] Exported {len(memories)} memories to [bold]{out_path}[/]")


# ── cortec doctor ─────────────────────────────────────────────────────────────

@main.command()
def doctor():
    """Health check — storage, security, and memory status."""
    db     = _db()
    vector = _vector()
    counts = db.count()
    conflicts = db.list_conflicts()

    table = Table(title="Cortec Doctor", box=box.ROUNDED, border_style="green")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail")

    checks = [
        ("Storage path",      paths.base.exists(),      str(paths.base)),
        ("SQLite DB",         paths.db.exists(),         str(paths.db)),
        ("Chroma vector DB",  paths.chroma.exists(),     str(paths.chroma)),
        ("Archive directory", paths.archive.exists(),    str(paths.archive)),
        ("Total memories",    True,                      str(counts["total"])),
        ("Pending approval",  counts["pending"] == 0,    f"{counts['pending']} pending"),
        ("Conflicts",         len(conflicts) == 0,       f"{len(conflicts)} unresolved"),
        ("Vector index",      vector.count() >= 0,       f"{vector.count()} entries"),
    ]

    all_ok = True
    for label, ok, detail in checks:
        status_str = "[green]✓ OK[/]" if ok else "[red]✗ FAIL[/]"
        table.add_row(label, status_str, detail)
        if not ok:
            all_ok = False

    console.print(table)
    if all_ok:
        console.print("\n[green]All checks passed.[/]")
    else:
        console.print("\n[red]Some checks failed. Review above.[/]")
        sys.exit(1)


# ── cortec audit ─────────────────────────────────────────────────────────────

@main.command()
@click.option("--project", "-p", default=None, help="Filter by project.")
def audit(project: str | None):
    """Audit report — what was stored, when, and from where."""
    db       = _db()
    memories = db.list_all(project=project, approved_only=False)

    table = Table(title="Cortec Audit", box=box.SIMPLE, border_style="cyan")
    table.add_column("ID",         style="bold")
    table.add_column("Project")
    table.add_column("Type")
    table.add_column("Source")
    table.add_column("Confidence")
    table.add_column("Approved")
    table.add_column("Created")

    for m in memories:
        table.add_row(
            m["id"],
            m["project"],
            m["type"],
            m["source"],
            str(m["confidence"]),
            "[green]Yes[/]" if m["approved"] else "[yellow]Pending[/]",
            m["created_at"][:10],
        )

    console.print(table)
    console.print(f"\nTotal: {len(memories)} memories")
