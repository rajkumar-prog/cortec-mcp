"""
Cortec CLI — developer interface for memory management.
"""

import json
import sys
from pathlib import Path

import click
import httpx
from rich.console import Console
from rich.table import Table
from rich import box
from rich.panel import Panel

from .agents import pr_assistant, debug_assistant, portfolio as portfolio_agent
from .config import CortecPaths, Confidence, DEFAULT_PROJECT, validate_type
from . import graph as graph_module
from .github import fetch_commits, fetch_prs, fetch_issues
from .stackoverflow import fetch_from_url, build_pattern_summary, canonical_url
from .storage.db import MetadataStore
from .storage.vector import VectorStore
from .security.scanner import scan
from .security.redactor import redact

console = Console()
paths = CortecPaths()


def _db() -> MetadataStore:
    """Initialise storage paths and return a MetadataStore instance."""
    paths.init()
    return MetadataStore(paths.db)


def _vector() -> VectorStore:
    """Initialise storage paths and return a VectorStore instance."""
    paths.init()
    return VectorStore(paths.chroma)


@click.group()
@click.version_option(package_name="cortec-mcp")
def main():
    """Cortec — local-first memory for developer workflows."""


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
        console.print("[green]Created[/] .cortec/CORTEC.md")
    console.print(f"[green]✓[/] Cortec initialized for project: [bold]{project}[/]")
    console.print(f"  Storage: {paths.base}")


@main.command()
@click.argument("text")
@click.option("--project", "-p", default=DEFAULT_PROJECT, help="Project name.")
@click.option("--type", "-t", default="general", help="Memory type.")
@click.option("--source", "-s", default="session", help="Memory source.")
@click.option("--tags", multiple=True, help="Tags (repeatable).")
@click.option("--auto", is_flag=True, help="Store without approval prompt.")
def remember(text, project, type, source, tags, auto):
    """Store a memory. Prompts for approval by default."""
    clean = redact(text)
    result = scan(clean)
    if not result.clean:
        console.print(f"[red]✗ Secret scan failed:[/] {', '.join(result.findings)}")
        sys.exit(1)

    try:
        type = validate_type(type)
    except ValueError as e:
        console.print(f"[red]✗[/] {e}")
        sys.exit(1)

    db = _db()
    vector = _vector()
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


@main.command()
@click.argument("query")
@click.option("--project", "-p", default=None, help="Limit to a project.")
@click.option("--type", "-t", default=None, help="Filter by type: decision, bug, fix, architecture, preference, command, dependency, portfolio, resume, general.")
@click.option("--top", "-n", default=5, help="Number of results.")
def recall(query, project, type, top):
    """Retrieve memories matching a query."""
    db = _db()
    vector = _vector()

    if vector.count() == 0:
        console.print("[yellow]No memories stored yet. Use 'cortec remember' first.[/]")
        return

    if type:
        try:
            type = validate_type(type)
        except ValueError as e:
            console.print(f"[red]✗[/] {e}")
            return

    hits = vector.search(query, top_k=top, project=project, type_=type)
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


@main.command()
@click.argument("memory_id")
def forget(memory_id: str):
    """Permanently delete a memory by ID."""
    db = _db()
    vector = _vector()
    if click.confirm(f"Delete memory {memory_id}? This cannot be undone."):
        deleted = db.delete(memory_id)
        vector.delete(memory_id)
        if deleted:
            console.print(f"[green]✓[/] Deleted memory [bold]{memory_id}[/]")
        else:
            console.print(f"[red]Memory {memory_id} not found.[/]")


@main.command()
@click.argument("memory_id")
def approve(memory_id: str):
    """Approve a pending memory and index it."""
    db = _db()
    vector = _vector()
    meta = db.get(memory_id)
    if not meta:
        console.print(f"[red]Memory {memory_id} not found.[/]")
        return
    console.print(Panel(meta["summary"], title=f"Approve {memory_id}?", border_style="yellow"))
    if click.confirm("Approve and index?"):
        db.approve(memory_id)
        vector.add(memory_id, meta["summary"], {
            "project": meta["project"],
            "type": meta["type"],
            "source": meta["source"],
        })
        console.print(f"[green]✓[/] Memory [bold]{memory_id}[/] approved and indexed.")


@main.command()
@click.option("--project", "-p", default=None, help="Filter by project.")
def status(project: str | None):
    """Show memory counts and pending approvals."""
    db = _db()
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

    all_memories = db.list_all(project=project, approved_only=True)
    if all_memories:
        type_counts: dict[str, int] = {}
        for m in all_memories:
            t = m.get("type", "general")
            type_counts[t] = type_counts.get(t, 0) + 1

        type_table = Table(box=box.SIMPLE, show_header=True)
        type_table.add_column("Type", style="bold")
        type_table.add_column("Count", justify="right")
        for t, n in sorted(type_counts.items(), key=lambda x: -x[1]):
            type_table.add_row(t, str(n))
        console.print("\n[bold]Memory breakdown by type:[/]")
        console.print(type_table)

    if pending:
        console.print(f"\n[yellow]Pending memories ({len(pending)}):[/]")
        for m in pending:
            console.print(f"  [bold]{m['id']}[/]  {m['summary'][:60]}…")
        console.print("\nRun [bold]cortec approve <id>[/] to index a memory.")

    open_conflicts = db.list_conflicts(resolved=False)
    if open_conflicts:
        console.print(f"\n[red]⚠ {len(open_conflicts)} unresolved conflict(s).[/] Run [bold]cortec conflicts[/] to review.")


@main.command()
@click.option("--project", "-p", default=None, help="Filter by project.")
@click.option("--out", "-o", default="cortec_export.json", help="Output file.")
def export(project: str | None, out: str):
    """Export all memories to a JSON file."""
    db = _db()
    memories = db.list_all(project=project, approved_only=False)
    out_path = Path(out)
    out_path.write_text(json.dumps(memories, indent=2))
    console.print(f"[green]✓[/] Exported {len(memories)} memories to [bold]{out_path}[/]")


@main.command()
def conflicts():
    """Show all unresolved memory conflicts."""
    db = _db()
    items = db.list_conflicts(resolved=False)

    if not items:
        console.print("[green]✓ No unresolved conflicts.[/]")
        return

    console.print(f"\n[red]⚠ {len(items)} unresolved conflict(s):[/]\n")
    for c in items:
        console.print(
            Panel(
                c["description"],
                title=f"Conflict [bold]{c['id']}[/]  —  memory {c['memory_id_a']}",
                subtitle=f"detected: {c['detected_at'][:10]}",
                border_style="red",
            )
        )
    console.print("\nTo resolve: [bold]cortec resolve <conflict_id>[/]")


@main.command()
@click.argument("conflict_id")
@click.option("--keep", "-k", default=None, help="Memory ID to keep.")
def resolve(conflict_id: str, keep: str | None):
    """Resolve a conflict by choosing which memory to keep."""
    db = _db()
    all_conflicts = db.list_conflicts(resolved=False)
    match = next((c for c in all_conflicts if c["id"] == conflict_id), None)

    if not match:
        console.print(f"[red]Conflict {conflict_id} not found or already resolved.[/]")
        return

    console.print(Panel(match["description"], title=f"Conflict {conflict_id}", border_style="yellow"))

    if not keep:
        keep = click.prompt("Enter memory ID to keep")

    # The conflicting memory is memory_id_a — drop it if user wants to keep something else
    drop_id = match["memory_id_a"] if keep != match["memory_id_a"] else None

    if drop_id:
        vector = _vector()
        db.delete(drop_id)
        vector.delete(drop_id)
        console.print(f"[green]✓[/] Deleted memory [bold]{drop_id}[/].")

    with db._conn() as conn:
        conn.execute("UPDATE conflicts SET resolved = 1 WHERE id = ?", (conflict_id,))
    console.print(f"[green]✓[/] Conflict {conflict_id} resolved.")


@main.command()
def doctor():
    """Health check — storage, security, and memory status."""
    db = _db()
    vector = _vector()
    counts = db.count()
    open_conflicts = db.list_conflicts(resolved=False)

    table = Table(title="Cortec Doctor", box=box.ROUNDED, border_style="green")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail")

    checks = [
        ("Storage path",      paths.base.exists(),         str(paths.base)),
        ("SQLite DB",         paths.db.exists(),            str(paths.db)),
        ("Chroma vector DB",  paths.chroma.exists(),        str(paths.chroma)),
        ("Archive directory", paths.archive.exists(),       str(paths.archive)),
        ("Total memories",    True,                         str(counts["total"])),
        ("Pending approval",  counts["pending"] == 0,       f"{counts['pending']} pending"),
        ("Conflicts",         len(open_conflicts) == 0,     f"{len(open_conflicts)} unresolved"),
        ("Vector index",      vector.count() >= 0,          f"{vector.count()} entries"),
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


@main.command()
@click.option("--project", "-p", default=None, help="Filter by project.")
def audit(project: str | None):
    """Audit report — what was stored, when, and from where."""
    db = _db()
    memories = db.list_all(project=project, approved_only=False)

    table = Table(title="Cortec Audit", box=box.SIMPLE, border_style="cyan")
    table.add_column("ID", style="bold")
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


@main.command("github-index")
@click.argument("repo")
@click.option("--project", "-p", default=DEFAULT_PROJECT, help="Project to store memories under.")
@click.option("--commits", default=20, help="Number of commits to index.")
@click.option("--prs", default=10, help="Number of pull requests to index.")
@click.option("--issues", default=10, help="Number of issues to index.")
def github_index(repo: str, project: str, commits: int, prs: int, issues: int):
    """Index a GitHub repo's commits, PRs, and issues as memories.

    REPO format: owner/repo  (e.g. rajkumar-prog/cortec-mcp)
    """
    db = _db()
    vector = _vector()
    stored = 0
    skipped = 0

    def _store(summary: str, type_: str, source: str, sha: str | None = None) -> None:
        """Redact, scan, and insert a single memory, updating stored/skipped counters."""
        nonlocal stored, skipped
        clean = redact(summary)
        if not scan(clean).clean:
            skipped += 1
            return
        mid = db.insert(
            summary=clean, project=project, type_=type_,
            source=source, confidence=0.8,
            approved=True, commit_sha=sha,
        )
        vector.add(mid, clean, {"project": project, "type": type_, "source": source})
        stored += 1

    try:
        commit_list = fetch_commits(repo, limit=commits)
        for c in commit_list:
            if c.message.strip():
                _store(
                    f"[{c.sha}] {c.message} — by {c.author} on {c.date[:10]}",
                    type_="fix", source="github_commit", sha=c.sha,
                )
        console.print(f"[green]✓[/] Indexed {len(commit_list)} commits")
    except RuntimeError as e:
        console.print(f"[yellow]⚠ Commits skipped:[/] {e}")

    try:
        pr_list = fetch_prs(repo, limit=prs)
        for pr in pr_list:
            text = f"PR #{pr.number}: {pr.title}"
            if pr.body:
                text += f"\n{pr.body}"
            _store(text, type_="fix", source="github_pr")
        console.print(f"[green]✓[/] Indexed {len(pr_list)} pull requests")
    except RuntimeError as e:
        console.print(f"[yellow]⚠ PRs skipped:[/] {e}")

    try:
        issue_list = fetch_issues(repo, limit=issues)
        for issue in issue_list:
            text = f"Issue #{issue.number} ({issue.state}): {issue.title}"
            if issue.body:
                text += f"\n{issue.body}"
            _store(text, type_="bug", source="github_issue")
        console.print(f"[green]✓[/] Indexed {len(issue_list)} issues")
    except RuntimeError as e:
        console.print(f"[yellow]⚠ Issues skipped:[/] {e}")

    console.print(f"\n[bold]Done.[/] Stored: [green]{stored}[/]  Skipped (secret scan): [yellow]{skipped}[/]")


@main.command("github-link")
@click.argument("memory_id")
@click.argument("commit_sha")
def github_link(memory_id: str, commit_sha: str):
    """Link a memory to a specific GitHub commit SHA.

    \b
    Example:
      cortec github-link a1b2c3d4 79ac0d5e
    """
    db = _db()
    meta = db.get(memory_id)
    if not meta:
        console.print(f"[red]Memory {memory_id} not found.[/]")
        return
    updated = db.link_to_commit(memory_id, commit_sha)
    if updated:
        console.print(
            f"[green]✓[/] Memory [bold]{memory_id}[/] linked to commit [bold]{commit_sha}[/]"
        )
    else:
        console.print("[red]Failed to link memory.[/]")


@main.command("so-store")
@click.argument("url")
@click.option("--project", "-p", default=DEFAULT_PROJECT, help="Project to store the pattern under.")
@click.option("--tags", multiple=True, help="Tags (repeatable).")
def so_store(url: str, project: str, tags: tuple):
    """Fetch a Stack Overflow answer or question and store it as a pattern memory.

    \b
    Example:
      cortec so-store https://stackoverflow.com/a/11227902
      cortec so-store https://stackoverflow.com/questions/231767/what-does-the-yield-keyword-do
    """
    db = _db()
    vector = _vector()

    url = canonical_url(url)
    existing = db.get_by_so_url(url)
    if existing:
        console.print(f"[yellow]Already stored as memory[/] [bold]{existing['id']}[/]")
        return

    console.print(f"Fetching [cyan]{url}[/] ...")
    try:
        content = fetch_from_url(url)
    except ValueError as e:
        console.print(f"[red]✗[/] {e}")
        return
    except httpx.RequestError as e:
        console.print(f"[red]✗ Network error:[/] {e}")
        return
    except RuntimeError as e:
        console.print(f"[red]✗[/] {e}")
        return

    summary = build_pattern_summary(content)
    clean = redact(summary)

    if not scan(clean).clean:
        console.print("[red]✗ Secret scan failed on fetched content.[/]")
        return

    console.print(Panel(clean[:400], title="Pattern to store", border_style="yellow"))
    if not click.confirm("Store this pattern?"):
        console.print("[yellow]Cancelled.[/]")
        return

    memory_id = db.insert(
        summary=clean,
        project=project,
        type_="pattern",
        source="stackoverflow",
        confidence=Confidence.STACKOVERFLOW,
        tags=list(tags),
        approved=True,
        so_url=url,
    )
    vector.add(memory_id, clean, {"project": project, "type": "pattern", "source": "stackoverflow"})
    console.print(f"[green]✓[/] Pattern stored as memory [bold]{memory_id}[/]  (confidence: {Confidence.STACKOVERFLOW})")


@main.command("so-search")
@click.argument("query")
@click.option("--project", "-p", default=None, help="Limit to a project.")
@click.option("--top", "-n", default=5, help="Number of results.")
def so_search(query: str, project: str | None, top: int):
    """Search stored Stack Overflow patterns by query."""
    db = _db()
    vector = _vector()

    if vector.count() == 0:
        console.print("[yellow]No memories stored yet.[/]")
        return

    hits = vector.search(query, top_k=top, project=project, type_="pattern")
    if not hits:
        console.print(f"[yellow]No patterns found for:[/] {query}")
        return

    for hit in hits:
        meta = db.get(hit["id"])
        if not meta:
            continue
        so_url = meta.get("so_url") or ""
        console.print(
            Panel(
                hit["document"][:300],
                title=f"[bold]{hit['id']}[/]  score={hit['score']}",
                subtitle=f"source=stackoverflow  {so_url}  {meta['created_at'][:10]}",
                border_style="cyan",
            )
        )


@main.command("graph-summary")
@click.option("--project", "-p", default=DEFAULT_PROJECT, help="Project to graph.")
def graph_summary(project: str):
    """Show a knowledge graph summary for a project — nodes, edges, components."""
    db = _db()
    memories = db.list_all(project=project, approved_only=True)
    if not memories:
        console.print(f"[yellow]No memories found for project:[/] {project}")
        return

    G = graph_module.build(memories)
    s = graph_module.summary(G)

    console.print(Panel(
        f"[bold]Nodes:[/]       {s['nodes']}\n"
        f"[bold]Edges:[/]       {s['edges']}\n"
        f"[bold]Components:[/]  {s['components']}\n"
        f"[bold]Largest:[/]     {s.get('largest_component', 0)} memories\n"
        f"[bold]Edge types:[/]  {s.get('edge_breakdown', {})}",
        title=f"Knowledge Graph — {project}",
        border_style="magenta",
    ))

    if s.get("most_connected"):
        mc = s["most_connected"]
        console.print(
            f"\n[bold]Most connected:[/] [cyan]{mc['id']}[/] "
            f"({mc['degree']} connections)\n  {mc['summary']}"
        )


@main.command("graph-neighbors")
@click.argument("memory_id")
@click.option("--depth", "-d", default=1, help="Hop depth (default 1).")
def graph_neighbors(memory_id: str, depth: int):
    """Show memories connected to a given memory in the knowledge graph.

    \b
    Example:
      cortec graph-neighbors a1b2c3d4
      cortec graph-neighbors a1b2c3d4 --depth 2
    """
    db = _db()
    meta = db.get(memory_id)
    if not meta:
        console.print(f"[red]Memory {memory_id} not found.[/]")
        return

    project = meta.get("project", DEFAULT_PROJECT)
    memories = db.list_all(project=project, approved_only=True)
    G = graph_module.build(memories)
    nbs = graph_module.neighbors(G, memory_id, depth=depth)

    if not nbs:
        console.print(f"[yellow]No neighbors found for[/] [bold]{memory_id}[/]")
        return

    console.print(f"\n[bold]Neighbors of[/] [cyan]{memory_id}[/] (depth={depth}):\n")
    table = Table(box=box.SIMPLE, show_header=True)
    table.add_column("ID", style="bold cyan")
    table.add_column("Type")
    table.add_column("Connection")
    table.add_column("Weight", justify="right")
    table.add_column("Summary")

    for nb in nbs:
        table.add_row(
            nb["id"],
            nb.get("type", ""),
            nb.get("connection", ""),
            str(nb.get("weight", "")),
            nb.get("summary", "")[:60],
        )
    console.print(table)


@main.command("graph-link")
@click.argument("memory_id_a")
@click.argument("memory_id_b")
def graph_link(memory_id_a: str, memory_id_b: str):
    """Explicitly link two memories in the knowledge graph.

    \b
    Example:
      cortec graph-link a1b2c3d4 e5f6g7h8
    """
    db = _db()
    if not db.get(memory_id_a):
        console.print(f"[red]Memory {memory_id_a} not found.[/]")
        return
    if not db.get(memory_id_b):
        console.print(f"[red]Memory {memory_id_b} not found.[/]")
        return

    linked = db.link_memories(memory_id_a, memory_id_b)
    if linked:
        console.print(
            f"[green]✓[/] Linked [bold]{memory_id_a}[/] ↔ [bold]{memory_id_b}[/]"
        )
    else:
        console.print("[red]Failed to link memories.[/]")


@main.command("pr-draft")
@click.option("--project", "-p", default=DEFAULT_PROJECT, help="Project name.")
@click.option("--context", "-c", default="", help="Optional description of the change.")
@click.option("--top", "-n", default=8, type=click.IntRange(min=1), help="Number of semantic results to surface.")
def pr_draft(project: str, context: str, top: int):
    """Draft a PR summary from project memory — decisions, fixes, and bugs.

    \b
    Example:
      cortec pr-draft --project myapp
      cortec pr-draft --project myapp --context "refactor auth middleware"
    """
    db = _db()
    vector = _vector()
    result = pr_assistant.draft(db, vector, project=project, context=context, top_k=top)

    if result["total_memories"] == 0:
        console.print(f"[yellow]No memories found for project:[/] {project}")
        return

    console.print(Panel(
        result["template"],
        title=f"PR Draft — {project}",
        border_style="green",
    ))

    stats = (
        f"decisions={len(result['decisions'])}  "
        f"fixes={len(result['fixes'])}  "
        f"bugs={len(result['bugs'])}  "
        f"relevant={len(result['relevant'])}"
    )
    console.print(f"[dim]{stats}[/]")


@main.command("debug")
@click.argument("error")
@click.option("--project", "-p", default=None, help="Limit to a project.")
@click.option("--top", "-n", default=5, type=click.IntRange(min=1), help="Number of suggestions.")
def debug_cmd(error: str, project: str | None, top: int):
    """Search memory for bugs, fixes, and patterns related to an error.

    \b
    Example:
      cortec debug "TypeError: cannot unpack non-sequence NoneType"
      cortec debug "connection refused port 5432" --project myapp
    """
    db = _db()
    vector = _vector()
    result = debug_assistant.suggest(db, vector, error=error, project=project, top_k=top)

    if result.get("message"):
        console.print(f"[yellow]{result['message']}[/]")
        return

    if not result["suggestions"]:
        console.print(f"[yellow]No matching memories found for:[/] {error}")
        return

    console.print(f"\n[bold]Debug suggestions for:[/] {error[:80]}\n")
    for s in result["suggestions"]:
        type_color = {"bug": "red", "fix": "green", "pattern": "cyan"}.get(s["type"], "white")
        so_line = f"  [dim]{s['so_url']}[/]" if s.get("so_url") else ""
        console.print(
            Panel(
                s["summary"][:300] + so_line,
                title=f"[bold]{s['id']}[/]  [{type_color}]{s['type']}[/]  score={s['score']}",
                subtitle=f"source={s['source']}  {s['created_at']}  confidence={s['confidence']}",
                border_style=type_color,
            )
        )


@main.command("portfolio")
@click.option("--project", "-p", default=None, help="Project (omit for all).")
@click.option("--markdown", "-m", is_flag=True, help="Print raw Markdown export.")
def portfolio_cmd(project: str | None, markdown: bool):
    """Build a portfolio summary from portfolio and resume memories.

    \b
    Example:
      cortec portfolio
      cortec portfolio --project myapp
      cortec portfolio --project myapp --markdown
    """
    db = _db()
    result = portfolio_agent.build(db, project=project)

    if markdown:
        console.print(result["markdown"])
        return

    label = project or "all projects"
    console.print(Panel(
        f"[bold]Portfolio items:[/]  {len(result['portfolio'])}\n"
        f"[bold]Resume entries:[/]   {len(result['resume'])}\n"
        f"[bold]Key decisions:[/]    {len(result['key_decisions'])}\n"
        f"[bold]Architecture:[/]     {len(result['architecture'])}\n"
        f"[bold]Total memories:[/]   {result['total_memories']}",
        title=f"Portfolio — {label}",
        border_style="magenta",
    ))

    if result["portfolio"]:
        console.print("\n[bold]Highlights:[/]")
        for item in result["portfolio"]:
            console.print(f"  [cyan]{item['id']}[/]  {item['summary'][:80]}  [dim]{item['created_at']}[/]")

    if result["resume"]:
        console.print("\n[bold]Achievements:[/]")
        for item in result["resume"]:
            console.print(f"  [cyan]{item['id']}[/]  {item['summary'][:80]}  [dim]{item['created_at']}[/]")

    if not result["portfolio"] and not result["resume"]:
        console.print(
            "\n[yellow]No portfolio or resume memories yet.[/]\n"
            "Store them with:\n"
            "  cortec remember '...' --type portfolio\n"
            "  cortec remember '...' --type resume"
        )
