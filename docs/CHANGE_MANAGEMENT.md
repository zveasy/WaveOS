# Change Management

## Release Approvals
- Require a review before tagging production releases.
- Verify SBOM and signatures in CI.

## Rollback
- Use `waveos bundle rollback` to restore the last known-good bundle.
- Validate rollback with a test run and report review.

## Operator Approval for Automated Recovery (DoD)

When recovery is enabled (`recovery_enabled=true`), WaveOS can run restart/degrade/reboot commands in response to ERROR/WARN events. For DoD and controlled environments:

1. **Require explicit approval** by setting `recovery_require_approval=true` (default when recovery is used). Recovery actions are always written to `recovery_actions.jsonl`; commands are **not** executed until approval is granted.
2. **Grant approval** by either:
   - Creating a file at `recovery_approval_path` (e.g. `out/recovery_approved`) with the single line `approved`, or
   - Setting `WAVEOS_RECOVERY_APPROVED=true` for that run (e.g. in a signed-off automation or operator script).
3. **Sign-off process:** A designated operator must review `recovery_actions.jsonl` (or the run report), confirm the proposed actions are appropriate, then create the approval file or run the pipeline with `WAVEOS_RECOVERY_APPROVED=true`. Document who is authorized to approve and retain logs per your audit policy.
4. **Hardware integration:** Point recovery commands to supervisor-owned scripts; see [Recovery Integration Kit](RECOVERY_INTEGRATION_KIT.md).
