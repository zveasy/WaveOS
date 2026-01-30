# Capacity Planning

## Inputs
- Expected links per device
- Samples per link per interval
- Retention window in days

## Estimation
- Storage per run = `samples * avg_record_size`
- Daily storage = `storage_per_run * runs_per_day`
- Allocate 2x headroom for spikes and evidence packs
