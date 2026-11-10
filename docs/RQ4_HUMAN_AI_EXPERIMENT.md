# Controlled human–AI experiment: prospective administration plan

No actual participant has been recruited or observed. All current observations are
invented engineering fixtures. One independent student administers this project;
software roles do not establish a research team or independent annotation.

## Design and allocation

Within-participant, two-period crossover:

- A = MANUAL_ONLY: de-identified authorized case, frozen taxonomy/handbook, no model
  label, score, explanation or review suggestion visible.
- B = AI_ASSISTED: equivalent task with frozen, eligible evaluated model suggestions.
  Make suggestion score semantics explicit; do not call margins/softmax calibrated
  confidence. Real effectiveness requires actual research-approved evaluated models.

Randomize AB/BA order with the recorded seed; counts differ by at most one if odd.
Sort pseudonyms before seeded shuffling for reproducibility. Within each participant,
allocate pairs from the same pre-rated easy/medium/hard stratum to opposite conditions,
randomize pair orientation, and avoid any repeated case **or group**. Default is three
cases per condition, a technical starting value, not a sufficient scientific design.
Set scientifically justified counts before freeze. Greedy exposure balancing favors
less-used cases, without guaranteeing globally equal exposure.

The pool must have sufficient distinct groups for matching. Difficulty is rated
prospectively from permitted evidence, independently of participant outcomes. Strata
are a coarse comparability control, not proof of equal difficulty. Record case groups,
taxonomy, pool checksum and model versions. Cases may be seen by different participants;
analysis accounts for crossed participant/case-group reuse.

## Independence and gold

Experimental cases must be separate from all model training, tuning, calibration and
protected final-test cases. Check IDs against frozen membership before gold labels
are read. Independent experiment gold uses disjoint, verified STEP 07 adjudicated
pilots with matching labels, source, version and artifact checksums. Reject an entire
pilot if its selection intersects development/test membership. Cross-version related
cases and content need documented human isolation review before allocation approval.

Reference annotators/adjudicator must be independent of the experiment participant;
verify the actual-person identity crosswalk privately, not just different role IDs.
No independent annotators are currently confirmed, so this is a real blocker.

Participant materials expose only case content and permitted suggestions; assignment
manifests contain no gold labels or gold-reference answer key. Coordinator gold maps
stay separate and protected. This step adds collection/analysis tools, not an RQ4
participant-facing web interface. Such an interface must preserve blinding and the
same gates before any live collection.

## Administration and measurement

Use a fixed instruction script and separate practice examples not in the pool. Offer
the same taxonomy, device, instructions and break policy in both conditions. Record
condition, period, within-period position and clock source. A break/washout policy
must be decided before collection; two periods cannot eliminate all carryover.

Start timing when the case becomes readable; stop on final submission. Use an
instrumented clock where possible, recording actual timezone-aware start/end events.
Manual clock entries must say MANUAL_CLOCK. Duration must match elapsed timestamps.
Do not replace missing clocks with means or synthetic values. End-less abandoned
tasks may have null end and duration. Record incomplete/abandoned rows; unobserved
assignments remain missing. Overlapping/reversed participant task sequences fail.

Record three human labels, suggestion snapshot, primary topic model reference and
all three task model references. Freeze references in allocation; do not swap models
mid-experiment. Unknown severity is a valid uncertain human response, not supervised
gold. Preserve original AI suggestions separately from human labels.

Operational acceptance means all final labels retain the displayed suggestions;
override means at least one differs. These measure label concordance, not a claim
about a participant's trust, reasoning or button click. Unmeasured flags remain null.

## Freeze and changes

`research assignments --source ...` requires a pre-collection package, current
consent and separate allocation approval, then writes an atomic immutable bundle.
Rerunning refuses overwrite. Pool, participant registry, model references, seed,
dataset binding and protocol must match at analysis time. Never silently reassign
after observation. Substantive design changes require prospective review and a new
experiment, preserving old assignments and deviations; participants still must not
repeat exposed cases under the new design.

Withdrawal prevents reporting retained observations from that participant. Remove
those observations through the documented protected steward process, preserve a
minimal withdrawal audit and submit a newly authorized package. Retain the original
allocation so withheld tasks remain visible as missing, not replacement observations.
Later re-consent does not restore observations preceding a withdrawal automatically.

## Interpretation

One researcher's self-test can check feasibility only. Mock assistance cannot support
an AI effectiveness claim. Lack of independent gold prevents accuracy-improvement
claims. Analyze learning/order, attrition and case reuse using the prespecified plan;
do not infer equivalence from absence of evidence or make administrative decisions.
