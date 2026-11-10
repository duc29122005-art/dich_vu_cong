# Vietnamese word segmentation

PhoBERT expects Vietnamese words segmented before BPE tokenization. Whitespace
splitting does not solve Vietnamese multi-syllable word segmentation. The pipeline
requires an explicit backend and records its version, model hashes, annotators,
heap configuration and conservative normalization version.

## Real backend: VnCoreNLP/RDRSegmenter

The stdlib Java adapter runs an already installed, reviewed local VnCoreNLP bundle.
It requires Java and these files in the configured model_directory:

```text
VnCoreNLP-1.2.jar
models/wordsegmenter/wordsegmenter.rdr
models/wordsegmenter/wordsegmenter.dict
```

No package, Java binary, jar or model is downloaded automatically. The declared
segmenter version must come from the manually verified distribution; filenames
alone do not establish version or authenticity. File hashes identify exact bytes.
Respect the segmenter distribution's license and acquisition conditions separately
from dataset and encoder permissions. Missing files/Java/version are readiness
blockers. No fallback is substituted.

The adapter invokes `java -Xmx512m -jar ... -fin ... -fout ... -annotators wseg`
with the local model directory as working directory. It reads the documented
tab-separated token-index/token output, joining segmented tokens with spaces.
Unknown output formats, invalid encoding, nonzero exit or timeout fail safely.
All child stdout/stderr are captured and never copied to logs or reports.

Input/output intermediates exist only in protected temporary directories under
data/private/phobert_segmenter and are removed after each invocation. On Windows,
the existing owner/SYSTEM ACL helper is reused; deployments must verify actual
account/storage protections. Removal is ordinary deletion, not secure erasure.
Only authorized sanitized data should reach this stage. Do not use unreviewed jars
or attacker-writable directories: local Java code is a trusted dependency.

V1 starts a JVM per record, prioritizing a small, explicit local adapter. This can
be slow for 2,000–5,000 records. A reviewed persistent VnCoreNLP process or verified
batch-preserving adapter is the upgrade when profiling demonstrates the need;
it must preserve record boundaries, model hashes and privacy controls.

Training and inference require exactly matching segmentation metadata. Local paths
are omitted from report metadata; provide the matching model location separately
when loading a real run. Normalization preserves accents, negation and punctuation;
no translation, spelling correction or inferred metadata is introduced.

## Synthetic fixture backend

`synthetic_fixture` is allowed only inside the existing internal temporary synthetic
session. It replaces a fixed list of invented-test phrases such as `thủ tục` with
`thủ_tục`. This is an explicit deterministic software fixture, **not a validated
Vietnamese segmenter**. It never authorizes research training, arbitrary external
input files or real-model readiness. Its tokenizer is synthetic WordLevel, not
PhoBERT BPE. Tests cover interface behavior, Unicode, negation, padding and truncation;
they do not measure real segmentation accuracy.

Until the actual VnCoreNLP bundle and genuine pretrained checkpoint are supplied
and independently reviewed, report both as unverified rather than claiming a
fully validated real PhoBERT pipeline.
