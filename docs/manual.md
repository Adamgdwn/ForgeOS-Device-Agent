# Manual

## What This Project Is

Describe the project in operator-friendly terms.

## How To Work In This Repo

1. Run `bash scripts/governance-preflight.sh`.
2. Review `project-control.yaml`.
3. Confirm the current roadmap and runbook still match reality.
4. Update docs when behavior or operating expectations change.

## Expected Outputs

- working code or deliverables
- current operational documentation
- a maintained roadmap
- reviewable governance records

## Operator Notes

- Device sessions infer `form_factor` as `phone`, `tablet`, or `unknown` from ADB/build/model evidence.
- Use the profile form's "Device type?" selector to leave detection on auto or override it when the model is ambiguous.
- Tablet/phone evidence influences use-case recommendations, but destructive actions remain governed by restore and approval gates.
