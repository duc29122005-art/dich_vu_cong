# Privacy screening audit

`audit_screen` extends STEP 04 screening with contextual case/file identifiers
and sensitive free-form cues. STEP 04's `screen` contract and publication gates
remain unchanged. Audit version is `privacy-audit-1`.

Categories: phone, email, citizen_id, personal_identifier (including labeled
account/passport/tax identifiers), address, personal_name, case_number and
sensitive_context. Structured matches receive safe placeholders. Name/address
markers and sensitive contexts flag review; they do not reliably redact complete
free-form names or addresses. New contextual case identifiers are redacted and
also flagged for review. Overlapping matches follow priority rules, so counts
represent detected categories, not independently counted overlapping patterns.

Reports contain only category counts, flagged-record counts and keyed references.
No matched values, raw IDs, raw metadata labels or unreviewed examples are written
to Markdown, JSON reports or logs. Audit artifacts remain protected and ignored
by Git; HMAC references and low-cardinality aggregates still require access and
retention controls. This implementation does not provide encryption, secure
deletion, differential privacy or a public reporting mechanism.

Automatic regex screening is not human-approved anonymization. It misses unmarked
Vietnamese names, unusual/obfuscated identifiers, free-form addresses and contextual
identification. It can confuse harmless administrative numbers with phone numbers.
Latin diacritics and multilingual cues do not establish identity or language.
Sensitive records require qualified human review in protected storage; findings
must not be copied into repository issues or public examples.

`tests/fixtures/privacy_audit_synthetic.json` contains 11 explicitly invented cases.
The offline coverage test computes 8 category true positives across all 8 supported
categories, 1 intentional false positive (a harmless number), and 1 intentional
false negative (an unmarked invented name). These are fixture coverage counts,
not scientific precision/recall or evidence of real-world anonymity. Decomposed
Unicode, redaction placeholders, negation and report-leak regressions are also
tested. Reassess patterns against authorized, reviewed evaluation data before
making research claims.

Every flagged row has unresolved audit review until an actual human clears it.
For SYNTHETIC data this generates WARN and never research publication eligibility.
For RESEARCH data unresolved risks generate FAIL even if STEP 04 previously
reviewed the records. Resolve new findings through the protected STEP 04 review
workflow and a newly versioned build. STEP 05 never grants privacy clearance.
Permissions, license, source provenance and review evidence remain mandatory;
no quality score or CLI flag can bypass them.
