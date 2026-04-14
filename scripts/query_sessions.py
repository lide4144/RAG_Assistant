#!/usr/bin/env python3
"""SQL query tool for session storage debugging.

This script provides a command-line interface for querying session data
stored in SQLite database.

Usage:
    python scripts/query_sessions.py [command] [options]

Commands:
    list                    List all sessions
    show <session_id>       Show details of a specific session
    turns <session_id>      Show all turns for a session
    stats                   Show database statistics
    query <sql>             Execute custom SQL query
    search <keyword>        Search sessions by keyword

Examples:
    # List recent sessions
    python scripts/query_sessions.py list --limit 10

    # Show specific session
    python scripts/query_sessions.py show abc-123

    # Search sessions
    python scripts/query_sessions.py search "GraphRAG"

    # Custom SQL query
    python scripts/query_sessions.py query "SELECT * FROM sessions WHERE updated_at > datetime('now', '-1 day')"

    # Show database stats
    python scripts/query_sessions.py stats
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def get_db_path() -> str:
    """Get database path from environment or default."""
    import os

    return os.environ.get("SESSION_SQLITE_PATH", "data/session_store.db")


def connect_db(db_path: str) -> sqlite3.Connection:
    """Connect to SQLite database."""
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}")
        print("Make sure SESSION_SQLITE_PATH is set correctly or use default path.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def cmd_list(db_path: str, limit: int = 20) -> None:
    """List all sessions."""
    conn = connect_db(db_path)
    cursor = conn.execute(
        """SELECT s.id, s.title, s.created_at, s.updated_at,
                  COUNT(st.turn_number) as turn_count
           FROM sessions s
           LEFT JOIN session_turns st ON s.id = st.session_id
           GROUP BY s.id
           ORDER BY s.updated_at DESC
           LIMIT ?""",
        (limit,),
    )

    rows = cursor.fetchall()
    if not rows:
        print("No sessions found.")
        return

    print(f"{'ID':<36} {'Turns':<6} {'Title':<50} {'Updated At'}")
    print("-" * 110)
    for row in rows:
        title = (row["title"] or "Untitled")[:48]
        print(f"{row['id']:<36} {row['turn_count']:<6} {title:<50} {row['updated_at']}")

    print(f"\nTotal: {len(rows)} session(s)")


def cmd_show(db_path: str, session_id: str) -> None:
    """Show details of a specific session."""
    conn = connect_db(db_path)

    # Get session info
    cursor = conn.execute(
        "SELECT * FROM sessions WHERE id = ?",
        (session_id,),
    )
    session = cursor.fetchone()

    if not session:
        print(f"Session not found: {session_id}")
        return

    print(f"Session: {session['id']}")
    print(f"Title: {session['title'] or 'Untitled'}")
    print(f"Created: {session['created_at']}")
    print(f"Updated: {session['updated_at']}")
    print()

    # Get turns
    cursor = conn.execute(
        """SELECT * FROM session_turns
           WHERE session_id = ?
           ORDER BY turn_number""",
        (session_id,),
    )
    turns = cursor.fetchall()

    print(f"Turns ({len(turns)}):")
    print("-" * 80)
    for turn in turns:
        print(f"\nTurn #{turn['turn_number']}:")
        print(f"  User: {turn['user_input'][:80] if turn['user_input'] else 'N/A'}...")
        print(
            f"  Query: {turn['standalone_query'][:80] if turn['standalone_query'] else 'N/A'}..."
        )
        print(f"  Answer: {turn['answer'][:100] if turn['answer'] else 'N/A'}...")
        print(f"  Decision: {turn['decision'] or 'N/A'}")

        # Parse JSON fields
        if turn["cited_chunk_ids"]:
            try:
                chunk_ids = json.loads(turn["cited_chunk_ids"])
                print(f"  Citations: {len(chunk_ids)} chunk(s)")
            except json.JSONDecodeError:
                pass

        if turn["entity_mentions"]:
            try:
                entities = json.loads(turn["entity_mentions"])
                print(f"  Entities: {', '.join(entities[:5])}")
            except json.JSONDecodeError:
                pass


def cmd_turns(db_path: str, session_id: str) -> None:
    """Show all turns for a session in detail."""
    conn = connect_db(db_path)

    cursor = conn.execute(
        """SELECT * FROM session_turns
           WHERE session_id = ?
           ORDER BY turn_number""",
        (session_id,),
    )
    turns = cursor.fetchall()

    if not turns:
        print(f"No turns found for session: {session_id}")
        return

    for turn in turns:
        print(f"\n{'=' * 80}")
        print(f"Turn #{turn['turn_number']} - {turn['created_at']}")
        print(f"{'=' * 80}")
        print(f"\nUser Input:\n{turn['user_input'] or 'N/A'}")
        print(f"\nStandalone Query:\n{turn['standalone_query'] or 'N/A'}")
        print(f"\nDecision: {turn['decision'] or 'N/A'}")
        print(f"\nAnswer:\n{turn['answer'][:500] if turn['answer'] else 'N/A'}...")

        # JSON fields
        if turn["cited_chunk_ids"]:
            try:
                chunk_ids = json.loads(turn["cited_chunk_ids"])
                print(f"\nCited Chunks: {chunk_ids}")
            except json.JSONDecodeError:
                pass

        if turn["entity_mentions"]:
            try:
                entities = json.loads(turn["entity_mentions"])
                print(f"Entities: {entities}")
            except json.JSONDecodeError:
                pass

        if turn["topic_anchors"]:
            try:
                anchors = json.loads(turn["topic_anchors"])
                print(f"Topic Anchors: {anchors}")
            except json.JSONDecodeError:
                pass

        if turn["output_warnings"]:
            try:
                warnings = json.loads(turn["output_warnings"])
                if warnings:
                    print(f"Warnings: {warnings}")
            except json.JSONDecodeError:
                pass

        if turn["planner_summary"]:
            try:
                summary = json.loads(turn["planner_summary"])
                if summary:
                    print(f"Planner Summary: {json.dumps(summary, indent=2)}")
            except json.JSONDecodeError:
                pass


def cmd_stats(db_path: str) -> None:
    """Show database statistics."""
    conn = connect_db(db_path)

    # Overall stats
    cursor = conn.execute("SELECT COUNT(*) FROM sessions")
    session_count = cursor.fetchone()[0]

    cursor = conn.execute("SELECT COUNT(*) FROM session_turns")
    turn_count = cursor.fetchone()[0]

    cursor = conn.execute("SELECT MAX(updated_at) FROM sessions")
    last_update = cursor.fetchone()[0]

    # Daily stats
    cursor = conn.execute(
        """SELECT DATE(created_at) as day, COUNT(*) as count
           FROM sessions
           GROUP BY DATE(created_at)
           ORDER BY day DESC
           LIMIT 7"""
    )
    daily_stats = cursor.fetchall()

    print("Database Statistics")
    print("=" * 50)
    print(f"Database Path: {db_path}")
    print(f"File Size: {Path(db_path).stat().st_size / 1024:.2f} KB")
    print(f"Total Sessions: {session_count}")
    print(f"Total Turns: {turn_count}")
    print(f"Last Update: {last_update}")

    if daily_stats:
        print(f"\nDaily Activity (Last 7 Days):")
        print(f"{'Date':<15} {'Sessions'}")
        print("-" * 30)
        for row in daily_stats:
            print(f"{row['day']:<15} {row['count']}")


def cmd_query(db_path: str, sql: str) -> None:
    """Execute custom SQL query."""
    conn = connect_db(db_path)

    # Safety check: only allow SELECT statements
    sql_clean = sql.strip().upper()
    if not sql_clean.startswith("SELECT"):
        print("Error: Only SELECT queries are allowed for safety.")
        sys.exit(1)

    try:
        cursor = conn.execute(sql)
        rows = cursor.fetchall()

        if not rows:
            print("Query returned no results.")
            return

        # Print headers
        headers = [desc[0] for desc in cursor.description]
        print(" | ".join(headers))
        print("-" * (len(" | ".join(headers)) + 10))

        # Print rows
        for row in rows:
            values = []
            for i, header in enumerate(headers):
                val = row[i]
                if val is None:
                    val = "NULL"
                elif isinstance(val, str) and len(val) > 50:
                    val = val[:47] + "..."
                values.append(str(val))
            print(" | ".join(values))

        print(f"\nTotal rows: {len(rows)}")

    except sqlite3.Error as e:
        print(f"SQL Error: {e}")
        sys.exit(1)


def cmd_search(db_path: str, keyword: str) -> None:
    """Search sessions by keyword."""
    conn = connect_db(db_path)

    search_pattern = f"%{keyword}%"
    cursor = conn.execute(
        """SELECT DISTINCT s.id, s.title, s.updated_at
           FROM sessions s
           LEFT JOIN session_turns st ON s.id = st.session_id
           WHERE s.title LIKE ?
              OR st.user_input LIKE ?
              OR st.answer LIKE ?
              OR st.standalone_query LIKE ?
           ORDER BY s.updated_at DESC""",
        (search_pattern, search_pattern, search_pattern, search_pattern),
    )

    rows = cursor.fetchall()
    if not rows:
        print(f"No sessions found matching: {keyword}")
        return

    print(f"Found {len(rows)} session(s) matching '{keyword}':")
    print()
    print(f"{'ID':<36} {'Updated':<20} {'Title'}")
    print("-" * 90)
    for row in rows:
        title = (row["title"] or "Untitled")[:40]
        print(f"{row['id']:<36} {row['updated_at']:<20} {title}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="SQL query tool for session storage debugging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--db",
        default=get_db_path(),
        help="Path to SQLite database (default: data/session_store.db)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list command
    list_parser = subparsers.add_parser("list", help="List all sessions")
    list_parser.add_argument(
        "--limit", type=int, default=20, help="Maximum sessions to show"
    )

    # show command
    show_parser = subparsers.add_parser("show", help="Show session details")
    show_parser.add_argument("session_id", help="Session ID to show")

    # turns command
    turns_parser = subparsers.add_parser("turns", help="Show all turns for a session")
    turns_parser.add_argument("session_id", help="Session ID")

    # stats command
    subparsers.add_parser("stats", help="Show database statistics")

    # query command
    query_parser = subparsers.add_parser("query", help="Execute custom SQL query")
    query_parser.add_argument("sql", help="SQL SELECT statement")

    # search command
    search_parser = subparsers.add_parser("search", help="Search sessions by keyword")
    search_parser.add_argument("keyword", help="Search keyword")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute command
    if args.command == "list":
        cmd_list(args.db, args.limit)
    elif args.command == "show":
        cmd_show(args.db, args.session_id)
    elif args.command == "turns":
        cmd_turns(args.db, args.session_id)
    elif args.command == "stats":
        cmd_stats(args.db)
    elif args.command == "query":
        cmd_query(args.db, args.sql)
    elif args.command == "search":
        cmd_search(args.db, args.keyword)


if __name__ == "__main__":
    main()
