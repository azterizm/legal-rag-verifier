# Proof of concept verdict

legal-rag-verifier 0.1.0, 2026-10-08. The verdict, the tests since 0.1.0 and item 1 of the last section updated 2026-10-16.

## Question

Can a generation loop catch an unsupported sentence while the answer is being written, cut it, give the model the
right statutory text and regenerate, so that a cheap model stays faithful to that text? The test is whether the
architecture holds on the data it was given. The accuracy of that data is not under test. Concurrency and failure
recovery were out of scope.

## Verdict

The architecture holds, with an LLM as the judge. Rollback, cache reuse and insertion of the source run on a
production inference server at low cost.

As first built, with a small entailment model as the auditor, the loop did not improve answers. On live output
most of its rejections were wrong: 1 of 12 by hand on software questions, 18 of 46 by a frontier model's labels
on statutes. Graded by hand, the loop's final answers were no better than one plain answer from the same model:
29 and 30 good against 32 of 40. That finding of 2026-10-08 stands for that auditor. The sections below describe
that system.

With Qwen 27B at 4 bits as generator and judge on one server, the loop improved answers on the tests run since.
The gain is where the generator answers from memory. With the source in the prompt there is almost nothing to
catch.

Share of hand-graded sentences each auditor judged right:

| Auditor | First test | Second test, 151 sentences |
|---|---|---|
| Qwen 27B judge | 93.8 % | 90.1 % |
| Entailment model | 68.7 % | 58.3 % |
| No auditor | 58.7 % | 55.6 % |

The first test has 358 graded sentences. The judge figure is on the 354 it scored.

The 27B loop run live:

| Run | Questions | Wrong without the loop | Wrong with the loop |
|---|---|---|---|
| Source in the prompt (stop 59) | 40 | 0 of 49 sentences | 0 of 49 sentences |
| Answer from memory (stop 59) | 40 | 36 of 65 sentences | 3 of 50 sentences, all refusals |
| Source in the prompt (stop 72) | 240 | 4 answers | 4 answers |

With the source in the prompt the loop took 1.9 s per answer at the median. On the 240 questions of stop 72,
answers holding a wrong sentence:

| Generator | Answers |
|---|---|
| Qwen 27B loop | 4 |
| Qwen 2.5 7B loop (stop 71) | 13 |
| Gemini 3.8 Flash | 3 |
| Claude Opus 4.6 | 8 |

This rests on 40 live questions for stop 59 and 240 for stops 68 to 72, on one server type, with greedy decoding
and one run per arm. Frontier models graded most sentences. The ones they left unsure or disagreed on were graded
by hand. A trained 1B model and two hosted decision APIs were tested as the judge and scored 2 to 8 points under
the 27B. The section Tests since 0.1.0 lists each step. The last section lists the changes required before a
production trial.

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

This section describes the system of 2026-10-08, with the entailment model as the auditor.

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

## Tests since 0.1.0

In order. Judge accuracy is the share of hand-graded sentences judged right, on the first test (358 sentences)
and the second (151). Wrong answers are answers holding a wrong sentence, of 240.

| Stop | Test | Result |
|---|---|---|
| 40 | Entailment model given the question | Passed right and wrong text alike. |
| 41 | Entailment model given facts derived from the source | Still failed on paraphrases. The claim check alone was more accurate. |
| 42 | Reasoning LLM as the entailment check | Gemini 3.8 Flash and Qwen 27B cut false rollbacks from 19 to 1 to 5 (Part A) and from 9 to 1 to 3 (Part B), and caught as many errors or more. MiniCheck and ModernBERT did not. |
| 43 to 47 | First test, 358 sentences graded by hand, 148 wrong | A judge that rolls back every sentence the source does not state scored 82 to 88 %, against 69 % for the entailment auditor and 73 to 75 % for a judge that rolls back only contradictions. A 7B trained on Gemini's labels scored 83 % at 1.7 s per clause, untrained 86 % at 3.9 s. On answers written with the source the best judge gained 3 of 163 sentences. |
| 48 | Signals read from the model: attention and likelihood | Did not separate right from wrong (AUROC 0.42 to 0.62, gate 0.65). |
| 50, 51 | Frontier models as the judge | Gemini 3.1 Pro 88.5 %, Claude Opus 5.5 89.1 %, Gemini 3.8 Flash 82.1 %, untrained Qwen 27B 88.3 %. |
| 52 | Figure rollbacks of the claim check sent to the judge | Qwen 27B 91.5 %, Opus 5.5 92.4 %. The claim check caught nothing the judge missed. Tuned on the test. |
| 53 | Question and source as written in the judge prompt | No gain. |
| 54 | Two notes stating the grader's standard | Qwen 27B 93.5 %. Tuned on the test. |
| 55, 56 | Second test, 151 unseen sentences | Tuned 90.1 %, untuned 89.4 %, no auditor 55.6 %. The notes are dropped. The 4-bit 27B matched 8-bit at half the time. On answers with the source the judge scored 88.9 % against 94.4 % for no auditor. |
| 57 | Qwen 27B as generator and judge | Wrong in 0 of 49 sentences with the source and 55 % closed-book, against 80 % for the 7B. Caught 35 of 36 wrong sentences. Rolled back 18 right ones, 16 of them refusals. |
| 59, 60 | The 27B loop live, 40 questions | See the verdict. The server reused the committed prefix on every retry. DeBERTa scored 58 % against 89 % for the judge. |
| 61, 65 | Judge reply without the reason | 93.8 % and 90.1 % at a third of the time per call. A live answer fell from 3.2 s to 1.9 s. |
| 62 to 64 | 1B judge trained on the 27B's labels | 89 % and 82 % at 0.06 s per call, 5 to 8 points under the 27B. With the 27B asked on each 1B rollback, 91 % and 85 %. |
| 66 | Hosted decision APIs as the judge | Jev 1.13 90.7 % and 88.1 %, OpenAI Decisions 89.0 % and 86.8 %. Neither within 3 points of the 27B on both tests. |
| 67 | Retries on 95 wrong closed-book sentences of the 7B | The default retry, which bans the first token, was wrong again 71 times. With the passage at the cursor, 16 to 25. The passage written into the KV cache was no better than a user turn. More attention on the passage made retries worse. |
| 68 | Closed-book loop, 3 generators | Wrong answers with the source as a turn: 27B 132 to 23, 7B 198 to 28, MiniCPM5-1B 92 to 53. The plain-text passage ended answers early. |
| 70 | Loop with the source in the prompt, 7B and 1B | 7B 25 to 13 (p = 0.045), 3.8 % refusals. 1B 116 to 46 to 49, 16 to 28 % refusals. A judge fault in the 1B runs was found and stop 68's 1B figures corrected. |
| 71 | 7B loop against frontier models | 7B loop 13, Claude Opus 4.6 8, Gemini 3.8 Flash 3, each checked by the other 1 or 2. Near none by the 4 point margin. The loop was fastest, 1.7 s against 3.1 to 9.0 s. |
| 72 | 27B loop against frontier models | 4, near every frontier arm. 2.0 s per answer. 1.35 right sentences per answer, against 1.79 and 2.12. The loop neither added nor removed errors. |
| 73 | ConSens (Iris.ai) with Llama 3.2 1B, no judge reply | Second test 81.5 %, threshold fixed on the first: 8.6 points under the 27B judge and told apart, 23 above the entailment model, at 30 ms per sentence against 0.54 s. It tells closed-book answers from grounded ones; it caught none of the 4 wrong sentences written with the source. |

## Required before production

1. Use an LLM as the judge. 89 % of the entailment auditor's rejections were right on planted errors. On live
   output it was 8 % by hand on software and 39 % by model labels on statutes. An untrained Qwen 27B is right on about 90 % of
   unseen sentences. Roll back every sentence the source does not state. Stop the segmenter splitting list
   numbers into sentences that the claim check rejects as figures. Confirm on a new graded set that figure
   rollbacks go to the judge (stop 52). Measure on real answers graded by people.
2. Insert the source as a user turn at the cut when the judge is an LLM. With the entailment model as the
   auditor, inserted retries were not better than a plain retry, and on statutes the model pasted the source.
   With the 27B judge the default retry, which bans the first token, was wrong again in 71 of 95 retries
   against 16 with the turn (stop 67), and the turn loop cut closed-book answers holding a wrong sentence from
   198 to 28 for the 7B (stop 68). The plain-text passage did better on retries but ended answers early in the
   live loop. Restate the question in the injected turn, as in the second version. Do not add a per-sentence
   relevance check. A single sentence of a correct answer often does not address the question on its own, so
   the check would reject correct text and exhaust the retries. Judge relevance on the whole answer.
3. Keep the router gate for abstention. Before the next run, fix a judge prompt that scores a refusal of a
   provision that does not exist as correct.
4. Reduce entailment errors on statutory drafting, starting with dropped qualifiers and rules judged against their
   exceptions.
5. Set the latency target from the measured cost of 69 to 117 ms per retry, or move to faster hardware.
6. Tune each change on the development set, then re-run the 103 test questions with the judge prompt fixed in advance.

Method: `docs/GRID.md`. Figures: `docs/measurements.md`. Raw results: `results/`. The trained 1B adapters: `huggingface.co/azterizm/minicpm5-1b-clause-judge`,
DOI `10.57967/hf/10885`.
