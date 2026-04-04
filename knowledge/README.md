# Knowledge Subsystem

This directory stores the controlled learning layer for ForgeOS.

It is designed to improve recommendations without allowing unsafe autonomous drift.

## Files

- `session_outcomes.json`: one record per device session
- `support_matrix.json`: aggregated evidence by device family

## Rules

- session evidence may improve confidence scores
- repeated observations may produce promotion candidates
- policy changes are never auto-applied from this directory alone
