# Technical demo walkthrough

Every dashboard page displays **SYNTHETIC DATA — DEMO ONLY**. The 420-record fixture
contains eight topics, three sentiments, three predicted severity levels, simulated
unknown reviewed severity, 20 missing event dates and simulated review/adjudication.
No independent human validation occurred. Seed controls reproducible opaque identifiers;
the mathematical counts and fixture dates stay fixed for explainable demonstrations.

1. Overview: inspect coverage, missingness and denominators. Complaint share does not
   measure population satisfaction or prove agency service quality.
2. Topic analysis: compare class support and demo agencies/domains. Small groups may be hidden.
3. Sentiment/severity: explicitly select predicted, reviewed or adjudicated basis.
   Simulated reviewed labels are not real gold.
4. Trends/alerts: select 2025-01-06–2025-01-13. Seven 40-case days precede a 120-case spike.
   Alerts explain baseline/support criteria; they are invented indicators, not incidents.
5. Model/review: distinguish `analytics-fixture-v1` seeded predictions from live
   `mock-fixture-v1` constant responses. Neither is a trained research model.

Use the protected parent shell from DEMO_QUICKSTART.md for a real API workflow over a
bundled synthetic case (not a citizen submission):

```powershell
$base = 'http://127.0.0.1:8000/api/v1'
$create = @{fixture_id=0; operation_id=[guid]::NewGuid().ToString()} | ConvertTo-Json
$item = Invoke-RestMethod "$base/feedback" -Method Post -Headers @{'X-API-Key'=$adminKey} -ContentType 'application/json' -Body $create
$id = $item.feedback_id
$claim = @{operation_id=[guid]::NewGuid().ToString(); expected_version=1; action='CLAIM'; reason_code='CLAIM'} | ConvertTo-Json
Invoke-RestMethod "$base/reviews/$id" -Method Patch -Headers @{'X-API-Key'=$reviewKey} -ContentType 'application/json' -Body $claim
$correction = @{operation_id=[guid]::NewGuid().ToString(); expected_version=2; action='CORRECT'; reason_code='CORRECTION'; labels=@{topic='fees'; sentiment='negative'; severity='high'}} | ConvertTo-Json
Invoke-RestMethod "$base/reviews/$id" -Method Patch -Headers @{'X-API-Key'=$reviewKey} -ContentType 'application/json' -Body $correction
Invoke-RestMethod "$base/reviews/$id/history" -Headers @{'X-API-Key'=$adminKey}
```

Original model predictions remain immutable. Repeating a stale expected_version returns
409; never retry by silently replacing someone else's version. ANALYST cannot edit or
read feedback text. New intake increases total feedback by one; prediction alone does not.
No API transition makes this case research gold. Restarting the API creates a fresh
isolated fixture with deterministic seed IDs and no accumulated duplicates. Seeding a
nonempty store is rejected. No existing database is reset.
