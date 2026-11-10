# Real dataset source research

Review date: 2026-11-04 (Asia/Bangkok). Candidate metadata is recorded separately
in `configs/acquisition_candidates.yaml`; it grants no permission and does not
modify `configs/dataset_sources.yaml` or permission evidence/history.

## Evidence collected

Only public metadata was requested. No feedback records, repository data files,
dataset shards, attachments or portal page bodies were downloaded.

| Check | Observed result | What it does not establish |
|---|---|---|
| HEAD `https://vpcp.dichvucong.gov.vn/` | HTTP 200; body not read | Owner identity, contact, fields, counts or reuse rights |
| GET `https://api.github.com/repos/doanhieung/vn-mps-public-service-dataset` | Repository metadata returned; `license: null`; description refers to Vietnamese public-service datasets sourced from the Ministry of Public Security portal | Original ownership, lawful redistribution, dataset suitability or absence of a license elsewhere |
| GET `https://huggingface.co/api/datasets?search=vietnamese%20public%20service&limit=10` | Empty catalog search result | Proof that no relevant licensed dataset exists |

The repository description is a publisher claim, not independently verified
ownership evidence. The search is narrow and not exhaustive. No additional
licensed Vietnamese individual public-service feedback corpus was verified.
UIT-VSFC remains an education benchmark; QA and aggregate satisfaction indicators
cannot substitute for labeled citizen feedback.

## Priority 1 — authorized_agency_export

- Owner, URL and contact route: **UNKNOWN** until an actual competent agency is identified.
- Relevance: preferred primary route, conditional on an approved de-identified export.
- Available fields, actual count, time coverage and PII risk: **UNKNOWN**.
- Requested size: approximately 2,000–5,000; this is a target, not an availability claim.
- License: **UNKNOWN**; permission: **PENDING**.
- Method: a documented agency export over a human-approved secure transfer channel.
- Next action: project owner identifies the data custodian, confirms their authority
  and contact independently, reviews/signs the generated Vietnamese request package.

## Priority 2 — public_service_official

- Candidate URL: https://vpcp.dichvucong.gov.vn/p/phananhkiennghi/pakn-tra-loi.html
- Owner and verified contact route: **UNKNOWN**. Reachability of a hostname is not
  verification of the legal data controller or authority to grant research rights.
- Relevance: candidate citizen complaints/feedback source from the project brief.
- Available fields, actual count, coverage, license and PII risk: **UNKNOWN**.
- Permission: **PENDING**; request target 2,000–5,000, not confirmed supply.
- Method: request a de-identified export; do not scrape the public page or invent an API.
- Next action: confirm the competent custodian and official request channel, then
  seek written analysis, annotation, training/evaluation and publication terms.

## Reference only — vn_mps_qa

URL: https://github.com/doanhieung/vn-mps-public-service-dataset

Owner/contact, actual fields/count/coverage and PII risk remain **UNKNOWN**.
License remains **UNKNOWN** because API metadata declares none; permission remains
**PENDING**. The existing registry classifies it as QA/terminology reference,
not labeled citizen feedback. Reception through the official-feedback acquisition
gate is blocked by its REFERENCE role. Verify original rights and content before
considering any future use; do not reinterpret QA questions as citizen complaints.

## Decision

`licensed_open_feedback` is an unverified discovery slot, not a registered source.
Its URL, owner, contact, fields, count, coverage and license are UNKNOWN;
availability is NOT_AVAILABLE. Register an actual source only after independently
verifying its identity, relevance and license. No new licensed corpus was verified
in this review; the earlier narrow metadata checks are not an exhaustive search.

| Candidate | Domain fit | Feasibility and bias | Missing evidence |
|---|---|---|---|
| authorized_agency_export | Preferred citizen-feedback route | Depends on agency cooperation; one agency may limit coverage | Custodian, fields, availability, rights and transfer approval |
| public_service_official | Candidate public-service feedback | Portal visibility does not establish export access or representativeness | Owner/contact, permitted export and reuse terms |
| vn_mps_qa | QA reference only | Questions are not labeled citizen-feedback records | Original ownership, license and content verification |
| licensed_open_feedback | UNKNOWN | No qualifying corpus verified | All source facts and license evidence |

Proceed with human contact and permission review for an agency export first.
No source is currently cleared for reception. Until authentic authorization and
transfer evidence exist, use only explicitly synthetic software fixtures.
