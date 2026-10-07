# Proof of concept verdict

legal-rag-verifier 0.1.0, 2026-10-07.

## Question

Can a generation loop catch an unsupported sentence while the answer is being written, cut it, give the model the
right statutory text and regenerate, so that a cheap model stays faithful to that text? The test is whether the
architecture holds on the data it was given. The accuracy of that data is not under test. Concurrency and failure
recovery were out of scope.

## Verdict

The architecture holds as a mechanism. It is not ready for production as built. Each part works on a production
inference server. The full loop makes the model faithful to the text it is given, but not to the question it was
asked. Two changes are required before a production trial. They are listed at the end.

## What was tested

An auditor checks each sentence against the provisions supplied with the question. It runs a rule-based check on
figures, citations, Act names, qualifiers and obligations, then a small entailment model (DeBERTa-v3 base). The
generator is Qwen 2.5 7B Instruct on SGLang, on one NVIDIA L4 GPU on Modal. Gemini 3.8 Flash, called through an
API, was the stronger reference model. When the auditor rejects a sentence, the engine cuts the answer back to the
start of that sentence and retries, at most 3 times per sentence. A retry either constrains the next tokens or, in
the last test, adds the provision text to the model's context as a new user turn. The added text never appears in
the answer. The comparisons used 103 UK statute questions that were never used to tune the auditor. 11 of them ask
about provisions that do not exist. A separate model, gpt-oss-120b, judged every final answer without knowing which
setup produced it. A blind sample of 80 answers was also labelled by hand.

## What holds

The auditor works at a usable rate. On a sealed test set it caught 80 % of planted errors and wrongly rejected
7.9 % of correct sentences. 89 % of its rejections were correct.

Rollback reuses the cache. Every retry on the server reused the text already processed, so only new tokens were
computed. A retry costs 117 ms on the L4 at bf16 and 69 ms at FP8, against 270 ms and 170 ms to reprocess the
prompt. The 30 ms target in the original specification cannot be met on this hardware. One forward pass of a 7B
model on an L4 takes about 53 ms.

Checking sentence by sentence releases output sooner. Qwen showed its first verified sentence after 3.8 s, against
8.1 s when the whole answer was checked first. Gemini showed the same pattern, 11.6 s against 16.1 s.

Adding the source makes a cheap model comply. With the provision added, the first retry passed the auditor 84 % of
the time after a rule-based rejection, against 28 % without it. After an entailment rejection the figures were
76 % and 41 %. Rejected sentences that ended in a refusal fell from 37 to 6. Every retry reused the cache.
Discarded tokens halved. Median time per answer fell from 7.9 s to 6.5 s. The judge found fewer answers with an
unsupported sentence, 17 against 22.

## What does not hold yet

The loop satisfies the auditor, not the question. The auditor checks that a sentence is supported, not that it
answers the question. Given a provision, Qwen writes something true from it, often a side clause. 21 of 50
recovered sentences were near-verbatim copies of the statute, against 1 of 41 without the source. Answers that did
not address the question rose from 13 to 24. The judge rated 61 % of answers correct with the source added, against
73 % without.

Abstention is lost. Without the source, the refusal sentence also handled questions about provisions that do not
exist. Adding the source replaces that refusal with a true but irrelevant sentence. Correct abstentions fell from
8 of 11 to 4 of 11.

The entailment model is the weakest part. It misreads double negatives in statutes, judges a correct rule against
its exception, and passes sentences that drop a qualifier. On the sealed set it caught 6 of 18 dropped qualifiers.
Across the four setups of the main comparison, the judge found 44 wrong sentences that the auditor passed, 23 of
them for a dropped qualifier.

Without the source, the sentence-level loop was less correct than a full retry on the same model, 73 % against
79 % on the judge. The hand-labelled sample pointed the other way, 18 against 16 of 20, so this result is not
settled. Gemini favoured the sentence-level loop, 88 % against 81 %.

## Limits of the evidence

The evidence covers 103 English questions on UK statutes, one GPU type, one small model and greedy decoding.
Each group has 25 to 40 rejected sentences, so small differences are not meaningful. The judge agreed with the hand
labels on 85 % of the sample (Cohen's kappa 0.375). Asked twice about 56 identical answers, it gave the same
verdict 49 times. Its figures show direction, not exact scores. A gap of 12 answers or more is outside that noise.
Concurrency, failure recovery and cost per answer were not measured.

## Required before production

1. Add a relevance signal. Restate the question in the injected turn, and check that each sentence addresses the
   question.
2. Add an abstention rule. When the question names a provision or Act that is not among the supplied provisions,
   refuse instead of adding the source.
3. Reduce entailment errors on statutory drafting, starting with dropped qualifiers and rules judged against their
   exceptions.
4. Set the latency target from the measured cost of 69 to 117 ms per retry, or move to faster hardware.
5. Tune each change on the development set, then re-run the 103 test questions with the same judge.

Method: `docs/GRID.md`. Figures: `docs/measurements.md`. Raw results: `results/grid/`. Decisions:
`docs/ROADMAP.md`.
