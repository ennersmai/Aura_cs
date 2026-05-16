# Panopticon Persistent Storage

This directory contains the SurrealDB database file (panopticon.db) using the
surrealkv backend. All geospatial data, aircraft telemetry, and OSINT events
are persisted here.

**Note**: This directory is git-ignored to prevent committing sensitive data.
Database files should NOT be committed to version control.

## Contents
- `panopticon.db` - SurrealDB database (auto-generated)
- `README.md` - This marker file

## Important
- Data persists across restarts
- Run `scripts/init_schema.surql` on first launch to initialize the database schema
- For a clean reset, delete the contents of this directory