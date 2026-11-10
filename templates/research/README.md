# Blank research collection templates

These CSV headers, empty JSONL files and JSON Schemas contain no participants,
consent or observations. Keep them blank in Git. Export working copies to protected
`data/private/research/` using `python -m pfa.cli research templates --output PATH`.

See [collection contracts](../../docs/RESEARCH_DATA_COLLECTION.md),
[participant information and consent](../../docs/RESEARCH_PARTICIPANT_CONSENT.md)
and [reporting commands](../../docs/RESEARCH_REPORTING_GUIDE.md).

All synthetic example records live in `pfa.research.smoke` and tests separately.
Schema validation alone grants no research, source, participant or gold approval.
