# Proof of concept verdict

legal-rag-verifier 0.1.0, 2026-10-08.

## Question

Can a generation loop catch an unsupported sentence while the answer is being written, cut it, give the model the
right statutory text and regenerate, so that a cheap model stays faithful to that text? The test is whether the
architecture holds on the data it was given. The accuracy of that data is not under test. Concurrency and failure
recovery were out of scope.

## Verdict

The architecture holds as a mechanism. Rollback, cache reuse and insertion of the source run on a production
inference server at low cost. It does not improve answers as built. The auditor decides when to roll back, and on
live output most of its rejections were wrong: 1 of 12 by hand on software questions, 18 of 46 by a frontier
model's labels on statutes. Graded by hand, the loop's final answers were no better than one plain answer from
the same model: 29 and 30 good against 32 of 40. Inserting the source makes retries pass the auditor. It does
not make them better. The changes required before a production trial are listed at the end.

## What was tested

An auditor checks each sentence against the provisions supplied with the question. It runs a rule-based check on
figures, citations, Act names, qualifiers and obligations, then a small entailment model (DeBERTa-v3 base). The
generator is Qwen 2.5 7B Instruct on SGLang, on one NVIDIA L4 GPU on Modal. Gemini 3.8 Flash, called through an
API, was the stronger reference model. When the auditor rejects a sentence, the engine cuts the answer back to the
start of that sentence and retries, at most 3 times per sentence. A retry either constrains the next tokens or, in
the last two tests, adds the provision text to the model's context as a new user turn. The added text never appears in
the answer. The comparisons used 103 UK statute questions that were never used to tune the auditor. 11 of them ask
about provisions that do not exist. A separate model, gpt-oss-120b, judged every final answer without knowing which
setup produced it. A blind sample of 80 answers was also labelled by hand.

## What holds

The auditor works at a usable rate. On a sealed test set it caught 80 % of planted errors and wrongly rejected
7.9 % of correct sentences. 89 % of its rejections were correct. That was measured on planted errors. On live model output
its rejections were far less often right; see below.

Rollback reuses the cache. Every retry on the server reused the text already processed, so only new tokens were
computed. A retry costs 117 ms on the L4 at bf16 and 69 ms at FP8, against 270 ms and 170 ms to reprocess the
prompt. The 30 ms target in the original specification cannot be met on this hardware. One forward pass of a 7B
model on an L4 takes about 53 ms.

Checking sentence by sentence releases output sooner. Qwen showed its first verified sentence after 3.8 s, against
8.1 s when the whole answer was checked first. Gemini showed the same pattern, 11.6 s against 16.1 s.

Adding the source makes a cheap model pass the auditor. With the provision added, the first retry passed the auditor 84 % of
the time after a rule-based rejection, against 28 % without it. After an entailment rejection the figures were
76 % and 41 %. Rejected sentences that ended in a refusal fell from 37 to 6. Every retry reused the cache.
Discarded tokens halved. Median time per answer fell from 7.9 s to 6.5 s. The judge found fewer answers with an
unsupported sentence, 17 against 22.

The effect comes from where the provision is placed, not from its presence. The provisions were already in the
system prompt. A second test retried 46 rejected sentences from the same state in five ways. Inserting the provision
at the cut point passed the auditor 39 times. The same text placed at the top of the prompt passed 17 times. A
retry without the provision passed 14 to 18 times. Clearing the cache before the retry changed no result, so the
cache saves time and does not change quality. The first request took 105 ms with the cache and 337 ms without it.

Insertion moves the model toward the provision. In all 46 states it made the regenerated sentence more likely. In
45 of 46 it made the rejected sentence less likely. The share of attention on provision text rose in all 46 states.
Most of it went to the inserted copy, and attention to the original copy halved. The shift carried into the next
sentence in all 18 states that had one.

## What does not hold yet

On live output the auditor's rejections were mostly wrong. On 40 software questions graded by hand, with
documentation quoted verbatim as the source, 1 of 12 rejected sentences was an error. The loop did not roll back on 5 of
the 8 wrong plain answers. 9 rollbacks fell on answers that were already correct. Retries were not better: good retries
7 with the source inserted, 8 with decode steering. Final answers were good 29 times (steering) and 30 times
(insertion), against 32 for one plain answer; the loop fixed 1 answer and made 3 worse, mostly by replacing correct
text with the refusal sentence.

The auditor's rejections and passes do not match sentence-level labels on statutes either. On the 46 shared rollback states, labelled
blind by Claude Opus 5.5 (model labels, not human), 18 of 46 rejected sentences were real errors, against 89 % on
the sealed battery. With the provision inserted, 33 of 46 retries were supported, against 17 with decode
steering, but only 11 were good: supported, on the question and reading on. 28 pasted the provision or started
mid-clause, and the auditor accepted that text. A retry with no provision, or with the provision at the top, was
good 26 times. The set target, more good retries with insertion than with steering, fails (11 against 17).

The loop satisfies the auditor, not the question. The auditor checks that a sentence is supported, not that it
answers the question. Given a provision, Qwen writes something true from it, often a side clause. 21 of 50
recovered sentences were near-verbatim copies of the statute, against 1 of 41 without the source. Answers that did
not address the question rose from 13 to 24. The judge rated 61 % of answers correct with the source added, against
73 % without. Insertion also ends answers early. The model stopped the answer right after an inserted retry in 28
of 46 states, against 17 of 44 after a plain retry.

A second version restated the question in the inserted turn. On the 92 questions that have an answer, it was
judged correct 67 times, the same as without the source and 8 more than the first version. Answers that did not
address the question fell from 16 to 12, still above 5 without the source. Answers with an unsupported sentence
fell to 13, against 20 without the source. These gaps are within the judge's noise. Restating the question
recovers part of the loss, not all of it.

Abstention is lost. Without the source, the refusal sentence also handled questions about provisions that do not
exist. Adding the source replaces that refusal with a true but irrelevant sentence. Correct abstentions fell from
8 of 11 to 4 of 11. In the second version, legal-rag-router ran before generation and refused exactly the 11
questions about provisions that do not exist, and no other. The judge rated all 11 refusals incorrect, because its
prompt accepts only claims the provisions support. The rule set before that run needed 75 of 103 correct and 8 of
11 abstentions. The second version scored 67 and 0, so it fails as written. The judge was not changed after the
run, and injection work stops for 0.1.0.

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
The attention and likelihood figures come from a separate replay that chose the same next token as the server 92
to 94 % of the time, below the 95 % set in advance. Attention shows where the model looked, not why it wrote what
it wrote. The likelihood figures carry the conclusion, and every effect pointed the same way in 45 or 46 of 46
states. Concurrency, failure recovery and cost per answer were not measured.

## Required before production

1. Raise the auditor's precision on live model output before anything else, and measure it on real generations
   graded by people, not on planted errors. The sealed battery's 89 % did not carry over: 8 % by hand on software,
   39 % by model labels on statutes. A rollback loop is only as good as its rejections.
   Giving the entailment model the question, in the answer or in the source, does not fix this (stop 40): it
   passes right and wrong text alike. Facts derived from the source in advance do not fix it either (stop 41):
   they remove the reasoning gap in cases like the ddof default, but the entailment model still fails on
   paraphrases of facts it is given, and the claim check alone was more accurate.
2. Treat insertion of the source as unproven: by hand and by model labels, inserted retries were not better than
   a plain retry, and on statutes the model pasted the source. If it is kept, restate the question in the
   injected turn, as in the second version. Do not add a per-sentence relevance
   check. A single sentence of a correct answer often does not address the question on its own, so the check
   would reject correct text and exhaust the retries. Judge relevance on the whole answer.
3. Keep the router gate for abstention. Before the next run, fix a judge prompt that scores a refusal of a
   provision that does not exist as correct.
4. Reduce entailment errors on statutory drafting, starting with dropped qualifiers and rules judged against their
   exceptions.
5. Set the latency target from the measured cost of 69 to 117 ms per retry, or move to faster hardware.
6. Tune each change on the development set, then re-run the 103 test questions with the judge prompt fixed in advance.

Method: `docs/GRID.md`. Figures: `docs/measurements.md`. Raw results: `results/grid/`. Decisions:
`docs/ROADMAP.md`.
