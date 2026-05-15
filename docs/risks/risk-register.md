# Risk Register

## Current Risk Classification

- Tier: Medium
- Owner: Adam Goodwin
- Last reviewed: 2026-05-15

## Key Risks

| ID | Risk | Likelihood | Impact | Controls | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R-001 | Destructive device actions could wipe data or make a device unrecoverable. | Medium | High | Dry-run default, restore-path requirement, explicit wipe phrase, install approval gate. | Adam Goodwin | Open |
| R-002 | Goal-directed automation could drift into unsupported lock bypass, unlicensed assets, or non-owner device modification. | Medium | High | Lawful-use attestation, research-only mode until attested, excluded feature list for lock bypass and unlicensed assets. | Adam Goodwin | Open |
| R-003 | Local self-learning could promote weak evidence into reusable master behavior. | Medium | Medium | Session-local learning, strategy memory snapshots, promotion candidates require validation and human review. | Adam Goodwin | Open |
| R-004 | Local model recommendations may be stale or hallucinated. | Medium | Medium | Deterministic policy guard, trusted-source provenance checks, worker transcripts, operator review. | Adam Goodwin | Open |
