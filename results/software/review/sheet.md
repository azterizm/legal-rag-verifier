# Stop 37 grading sheet (blind)

Grade every lettered text in `grades.csv`. Judge only against the documentation shown, not what
you know about the tool. Grade each text on its own, not against the others. `note` is optional.

- `correct`: "yes" if every claim in the text matches the documentation shown; "no" if any claim is
  wrong or not in the documentation.
- `answers`: "yes" if the text helps answer the question asked; "no" if it is about something else.
- `reads_well` (Part A only): "yes" if it is a complete sentence that continues the answer so far;
  "no" for pasted labels or headings, fragments, or a repeat of the answer so far.

# Part A: one rejected sentence and its retries, each read after the answer so far

---

## A01. What divisor does numpy.std use by default?

**Documentation:**

> [NumPy documentation, numpy.std, parameter ddof]
> Means Delta Degrees of Freedom. The divisor used in calculations is N - ddof, where N represents the number of elements. By default ddof is zero.

**Answer so far:** (nothing yet)

**A01A.** By default, the divisor used in calculations by `numpy.std` is \( N \), where \( N \) is the number of elements.

**A01B.** By default, numpy.std uses a divisor of N, where N is the number of elements.

**A01C.** numpy.std uses a divisor of N in its calculations by default, where N is the number of elements.


---

## A02. What does a 0.y.z version mean in Semantic Versioning, and when must the major version go up?

**Documentation:**

> [Semantic Versioning 2.0.0, item 4]
> Major version zero (0.y.z) is for initial development. Anything MAY change at any time. The public API SHOULD NOT be considered stable.
>
> [Semantic Versioning 2.0.0, item 8]
> Major version X (X.y.z | X > 0) MUST be incremented if any backward incompatible changes are introduced to the public API. It MAY also include minor and patch level changes. Patch and minor versions MUST be reset to 0 when major version is incremented.

**Answer so far:** A 0.y.z version in Semantic Versioning 2.0.0 indicates that the software is in initial development, and the public API is not considered stable.

**A02A.** Anything may change at any time.

**A02B.** Major version must be incremented when backward incompatible changes are introduced to the public API, with the minor and patch versions being reset to 0.

**A02C.** It MAY also include minor and patch level changes.


---

## A03. If I fix the random seed, are PyTorch results reproducible across CPU and GPU?

**Documentation:**

> [PyTorch 2.7 documentation, Reproducibility]
> Completely reproducible results are not guaranteed across PyTorch releases, individual commits, or different platforms. Furthermore, results may not be reproducible between CPU and GPU executions, even when using identical seeds.

**Answer so far:** Fixing the random seed does not guarantee that PyTorch results will be reproducible across CPU and GPU executions.

**A03A.** Completely reproducible results are not guaranteed even when using identical seeds for CPU and GPU executions.

**A03B.** According to the documentation, results may not be reproducible between CPU and GPU even when using identical seeds.

**A03C.** The documentation explicitly states that results may not be reproducible between CPU and GPU even when using identical seeds.


---

## A04. Can a Prometheus counter go down?

**Documentation:**

> [Prometheus documentation, Metric types, Counter]
> A counter is a cumulative metric that represents a single monotonically increasing counter whose value can only increase or be reset to zero on restart. For example, you can use a counter to represent the number of requests served, tasks completed, or errors.
>
> Do not use a counter to expose a value that can decrease. For example, do not use a counter for the number of currently running processes; instead use a gauge.

**Answer so far:** (nothing yet)

**A04A.** No, a Prometheus counter cannot go down.

**A04B.** A Prometheus counter cannot go down.


---

## A05. How should a JWT's exp claim be checked, and is any clock skew allowed?

**Documentation:**

> [RFC 7519, section 4.1.4 ("exp" (Expiration Time) Claim)]
> The "exp" (expiration time) claim identifies the expiration time on or after which the JWT MUST NOT be accepted for processing. The processing of the "exp" claim requires that the current date/time MUST be before the expiration date/time listed in the "exp" claim.
>
> Implementers MAY provide for some small leeway, usually no more than a few minutes, to account for clock skew. Its value MUST be a number containing a NumericDate value. Use of this claim is OPTIONAL.

**Answer so far:** (nothing yet)

**A05A.** To check a JWT's exp (expiration time) claim, the current date/time must be compared to the expiration date/time specified in the "exp" claim.

**A05B.** The "exp" claim should be checked by comparing the current date/time with the expiration date/time specified in the "exp" claim.

**A05C.** The "exp" (expiration time) claim in a JWT should be checked to ensure that the current date/time is before the expiration date/time specified in the "exp" claim.


---

## A06. What regularisation does scikit-learn's LogisticRegression use by default?

**Documentation:**

> [scikit-learn documentation, sklearn.linear_model.LogisticRegression, parameter penalty]
> 'l2': add an L2 penalty term and it is the default choice;
>
> Deprecated since version 1.8: penalty was deprecated in version 1.8 and will be removed in 1.10. Use l1_ratio and C instead.
>
> [scikit-learn documentation, sklearn.linear_model.LogisticRegression, parameter C]
> Inverse of regularization strength; must be a positive float. Like in support vector machines, smaller values specify stronger regularization. C=np.inf results in unpenalized logistic regression.

**Answer so far:** By default, scikit-learn's LogisticRegression uses an L2 penalty term, which is specified by the parameter `penalty='l2'`. However, note that the `penalty` parameter is deprecated since version 1.8 and will be removed in version 1.10.

**A06A.** Users are advised to use `l1_ratio` and `C` instead for specifying the type and strength of regularization.

**A06B.** The documentation does not explicitly state what regularisation method (L1, L2, or Elastic Net) is used by default.

**A06C.** Instead, you should use the `l1_ratio` and `C` parameters to control regularization.


---

## A07. What share of the data goes to the test set in scikit-learn's train_test_split by default?

**Documentation:**

> [scikit-learn documentation, sklearn.model_selection.train_test_split, parameter test_size]
> If float, should be between 0.0 and 1.0 and represent the proportion of the dataset to include in the test split. If int, represents the absolute number of test samples. If None, the value is set to the complement of the train size. If train_size is also None, it will be set to 0.25.

**Answer so far:** (nothing yet)

**A07A.** In scikit-learn's `train_test_split` by default, the test set gets 25% of the data.

**A07B.** If `test_size` is `None`, the value is set to the complement of the `train_size`.

**A07C.** By default, 25% of the data goes to the test set in scikit-learn's train_test_split when the test_size parameter is not specified.


---

## A08. What is the difference between the Cache-Control directives no-cache and no-store?

**Documentation:**

> [RFC 9111, section 5.2.2.4 (no-cache)]
> The no-cache response directive, in its unqualified form (without an argument), indicates that the response MUST NOT be used to satisfy any other request without forwarding it for validation and receiving a successful response; see Section 4.3.
>
> [RFC 9111, section 5.2.2.5 (no-store)]
> The no-store response directive indicates that a cache MUST NOT store any part of either the immediate request or the response and MUST NOT use the response to satisfy any other request.

**Answer so far:** The Cache-Control directive no-cache indicates that a cache MUST NOT use the response to satisfy a subsequent request without successful revalidation with the origin server.

**A08A.** The no-store directive, on the other hand, not only prevents the response from being used to satisfy any other request but also mandates that no part of the request or response be stored by the cache.

**A08B.** In contrast, the no-store directive is stricter, as it not only prevents the response from being used to satisfy a subsequent request but also mandates that no part of the response or the request be stored by a cache.

**A08C.** On the other hand, the Cache-Control directive no-store specifies that a cache MUST NOT store any part of the response, ensuring that the response is not cached at all.


---

## A09. What isolation level does PostgreSQL use by default, and does it support Read Uncommitted?

**Documentation:**

> [PostgreSQL 17 documentation, 13.2 Transaction Isolation]
> In PostgreSQL, you can request any of the four standard transaction isolation levels, but internally only three distinct isolation levels are implemented, i.e., PostgreSQL's Read Uncommitted mode behaves like Read Committed. This is because it is the only sensible way to map the standard isolation levels to PostgreSQL's multiversion concurrency control architecture.
>
> [PostgreSQL 17 documentation, 13.2.1 Read Committed Isolation Level]
> Read Committed is the default isolation level in PostgreSQL. When a transaction uses this isolation level, a SELECT query (without a FOR UPDATE/SHARE clause) sees only data committed before the query began; it never sees either uncommitted data or changes committed by concurrent transactions during the query's execution.

**Answer so far:** PostgreSQL uses the Read Committed isolation level by default.

**A09A.** It does not fully support the Read Uncommitted isolation level as defined in the standard;

**A09B.** PostgreSQL does not fully support the Read Uncommitted isolation level;

**A09C.** This means that PostgreSQL's Read Uncommitted mode is not truly Read Uncommitted but rather behaves like Read Committed.


---

## A10. Should I apply softmax to the model output before nn.CrossEntropyLoss?

**Documentation:**

> [PyTorch 2.7 documentation, torch.nn.CrossEntropyLoss]
> The input is expected to contain the unnormalized logits for each class (which do not need to be positive or sum to 1, in general).

**Answer so far:** (nothing yet)

**A10A.** No, you should not apply softmax to the model output before using `nn.CrossEntropyLoss`.

**A10B.** For `torch.nn.CrossEntropyLoss`, you should not apply `softmax` to the model output before passing it to the loss function.


---

## A11. Do WebSocket frames have to be masked, and in which direction?

**Documentation:**

> [RFC 6455, section 5.1 (Overview)]
> To avoid confusing network intermediaries (such as intercepting proxies) and for security reasons that are further discussed in Section 10.3, a client MUST mask all frames that it sends to the server (see Section 5.3 for further details). (Note that masking is done whether or not the WebSocket Protocol is running over TLS.) The server MUST close the connection upon receiving a frame that is not masked. In this case, a server MAY send a Close frame with a status code of 1002 (protocol error) as defined in Section 7.4.1. A server MUST NOT mask any frames that it sends to the client. A client MUST close a connection if it detects a masked frame.

**Answer so far:** (nothing yet)

**A11A.** WebSocket frames must be masked when sent from a client to a server, but not when sent from a server to a client.

**A11B.** A client MUST mask all frames that it sends to the server, and a server MUST NOT mask any frames that it sends to the client.

**A11C.** Client-to-server WebSocket frames must be masked, while server-to-client frames must not be masked.


---

## A12. What does round(2.5) return in Python?

**Documentation:**

> [Python 3 documentation, Built-in Functions, round()]
> For the built-in types supporting round(), values are rounded to the closest multiple of 10 to the power minus ndigits; if two multiples are equally close, rounding is done toward the even choice (so, for example, both round(0.5) and round(-0.5) are 0, and round(1.5) is 2). Any integer value is valid for ndigits (positive, zero, or negative). The return value is an integer if ndigits is omitted or None.

**Answer so far:** (nothing yet)

**A12A.** In Python, round(2.5) returns 0.

**A12B.** The return value is an integer if ndigits is omitted or None.

**A12C.** In Python, round(2.5) returns 2.


# Part B: whole answers

---

## B01. How is git push --force-with-lease safer than --force?

**Documentation:**

> [Git documentation, git-push, --force-with-lease]
> Imagine that you have to rebase what you have already published. You will have to bypass the "must fast-forward" rule in order to replace the history you originally published with the rebased history. If somebody else built on top of your original history while you are rebasing, the tip of the branch at the remote may advance with their commit, and blindly pushing with --force will lose their work.
>
> --force-with-lease alone, without specifying the details, will protect all remote refs that are going to be updated by requiring their current value to be the same as the remote-tracking branch we have for them.

**B01A.** `git push --force-with-lease` is safer than `git push --force` because it requires the current value of the remote ref to match the ref that is recorded in the local repository. This check helps prevent overwriting changes made by other contributors to the same branch since the last time you fetched updates. In contrast, `git push --force` does not perform this check and will overwrite the remote branch regardless of any changes others may have made.

**B01B.** `git push --force-with-lease` is safer than `git push --force` because it requires the current value of the remote ref to match the ref that is recorded in the local repository. This check helps prevent overwriting changes made by other contributors to the same branch since the last time you fetched from the remote repository. In contrast, `git push --force` will overwrite the remote branch regardless of whether changes have been made by others, potentially losing their work.


---

## B02. Does Python's json.dumps reject NaN values?

**Documentation:**

> [Python 3 documentation, json, json.dump() parameter allow_nan]
> allow_nan (bool) – If False, serialization of out-of-range float values (nan, inf, -inf) will result in a ValueError, in strict compliance with the JSON specification. If True (the default), their JavaScript equivalents (NaN, Infinity, -Infinity) are used.

**B02A.** By default, Python's `json.dumps` does not reject NaN values. If `allow_nan` is set to `False`, out-of-range float values like NaN will result in a ValueError. However, if `allow_nan` is set to `True` (the default), NaN values will be serialized as `NaN`.

**B02B.** By default, Python's `json.dumps` does not reject NaN values. If `allow_nan` is set to `False`, out-of-range float values like NaN will result in a `ValueError`. However, if `allow_nan` is set to `True` (the default), NaN values will be serialized to their JavaScript equivalents (NaN).


---

## B03. Should I apply softmax to the model output before nn.CrossEntropyLoss?

**Documentation:**

> [PyTorch 2.7 documentation, torch.nn.CrossEntropyLoss]
> The input is expected to contain the unnormalized logits for each class (which do not need to be positive or sum to 1, in general).

**B03A.** I cannot state this point reliably from the documentation provided. According to the documentation, the input to `torch.nn.CrossEntropyLoss` should contain the unnormalized logits for each class. It does not need to be normalized or have any specific properties like being positive or summing to 1. I cannot state this point reliably from the documentation provided.

**B03B.** No, you should not apply softmax to the model output before using `nn.CrossEntropyLoss`. The documentation specifies that the input to `nn.CrossEntropyLoss` should contain the unnormalized logits for each class.

**B03C.** The input to `torch.nn.CrossEntropyLoss` should contain the unnormalized logits for each class. Softmax is not applied to the model output before using `nn.CrossEntropyLoss`; the loss function applies softmax internally to the logits. I cannot state this point reliably from the documentation provided.


---

## B04. Are foreign keys enforced in SQLite by default?

**Documentation:**

> [SQLite, Foreign Key Support, 2. Enabling Foreign Key Support]
> Foreign key constraints are disabled by default (for backwards compatibility), so must be enabled separately for each database connection.

**B04A.** No, foreign key constraints are not enforced by default in SQLite. They must be enabled separately for each database connection.


---

## B05. What does calling model.eval() do in PyTorch?

**Documentation:**

> [PyTorch 2.7 documentation, torch.nn.Module.eval()]
> Set the module in evaluation mode.
>
> This has an effect only on certain modules. See the documentation of particular modules for details of their behaviors in training/evaluation mode, i.e. whether they are affected, e.g. Dropout, BatchNorm, etc.
>
> This is equivalent with self.train(False).

**B05A.** Calling `model.eval()` in PyTorch sets the module in evaluation mode. This method affects certain modules, such as Dropout and BatchNorm, by altering their behavior appropriate for evaluation. It is equivalent to `self.train(False)`.


---

## B06. What does a 0.y.z version mean in Semantic Versioning, and when must the major version go up?

**Documentation:**

> [Semantic Versioning 2.0.0, item 4]
> Major version zero (0.y.z) is for initial development. Anything MAY change at any time. The public API SHOULD NOT be considered stable.
>
> [Semantic Versioning 2.0.0, item 8]
> Major version X (X.y.z | X > 0) MUST be incremented if any backward incompatible changes are introduced to the public API. It MAY also include minor and patch level changes. Patch and minor versions MUST be reset to 0 when major version is incremented.

**B06A.** A 0.y.z version in Semantic Versioning 2.0.0 indicates that the software is in initial development, and the public API is not considered stable. Anything may change at any time. The major version must go up when backward incompatible changes are introduced to the public API.

**B06B.** A 0.y.z version in Semantic Versioning 2.0.0 indicates that the software is in initial development, and the public API is not considered stable. It MAY also include minor and patch level changes. I cannot state this point reliably from the documentation provided. I cannot state this point reliably from the documentation provided. I cannot state this point reliably from the documentation provided.

**B06C.** A 0.y.z version in Semantic Versioning 2.0.0 indicates that the software is in initial development, and the public API is not considered stable. Major version must be incremented when backward incompatible changes are introduced to the public API, with the minor and patch versions being reset to 0.


---

## B07. What is the difference between the Cache-Control directives no-cache and no-store?

**Documentation:**

> [RFC 9111, section 5.2.2.4 (no-cache)]
> The no-cache response directive, in its unqualified form (without an argument), indicates that the response MUST NOT be used to satisfy any other request without forwarding it for validation and receiving a successful response; see Section 4.3.
>
> [RFC 9111, section 5.2.2.5 (no-store)]
> The no-store response directive indicates that a cache MUST NOT store any part of either the immediate request or the response and MUST NOT use the response to satisfy any other request.

**B07A.** The Cache-Control directive no-cache indicates that a cache MUST NOT use the response to satisfy a subsequent request without successful revalidation with the origin server. The no-store directive, on the other hand, not only prevents the response from being used to satisfy any other request but also mandates that no part of the request or response be stored by the cache. Therefore, the key difference is that no-cache allows the response to be stored but requires it to be revalidated with the origin server before reuse, whereas no-store absolutely prohibits any storage of the request or response by the cache.

**B07B.** The Cache-Control directive no-cache indicates that a cache MUST NOT use the response to satisfy a subsequent request without successful revalidation with the origin server. On the other hand, the Cache-Control directive no-store specifies that a cache MUST NOT store any part of the response, ensuring that the response is not cached at all.

**B07C.** The Cache-Control directive no-cache indicates that a cache MUST NOT use the response to satisfy a subsequent request without successful revalidation with the origin server. In contrast, the no-store directive is stricter, as it not only prevents the response from being used to satisfy a subsequent request but also mandates that no part of the response or the request be stored by a cache.


---

## B08. Can a PostgreSQL column with a UNIQUE constraint hold more than one NULL?

**Documentation:**

> [PostgreSQL 17 documentation, 5.5.3 Unique Constraints]
> In general, a unique constraint is violated if there is more than one row in the table where the values of all of the columns included in the constraint are equal. By default, two null values are not considered equal in this comparison. That means even in the presence of a unique constraint it is possible to store duplicate rows that contain a null value in at least one of the constrained columns. This behavior can be changed by adding the clause NULLS NOT DISTINCT

**B08A.** Yes, a PostgreSQL column with a UNIQUE constraint can hold more than one NULL value. By default, two NULL values are not considered equal in the context of a unique constraint, meaning multiple rows can have NULL in the constrained column without violating the unique constraint.

**B08B.** Yes, a PostgreSQL column with a UNIQUE constraint can hold more than one NULL value. By default, two null values are not considered equal in the context of a unique constraint, which means that multiple rows can have NULL in the constrained column without violating the unique constraint.


---

## B09. What isolation level does PostgreSQL use by default, and does it support Read Uncommitted?

**Documentation:**

> [PostgreSQL 17 documentation, 13.2 Transaction Isolation]
> In PostgreSQL, you can request any of the four standard transaction isolation levels, but internally only three distinct isolation levels are implemented, i.e., PostgreSQL's Read Uncommitted mode behaves like Read Committed. This is because it is the only sensible way to map the standard isolation levels to PostgreSQL's multiversion concurrency control architecture.
>
> [PostgreSQL 17 documentation, 13.2.1 Read Committed Isolation Level]
> Read Committed is the default isolation level in PostgreSQL. When a transaction uses this isolation level, a SELECT query (without a FOR UPDATE/SHARE clause) sees only data committed before the query began; it never sees either uncommitted data or changes committed by concurrent transactions during the query's execution.

**B09A.** PostgreSQL uses the Read Committed isolation level by default. PostgreSQL does not fully support the Read Uncommitted isolation level; instead, it behaves as if Read Uncommitted were mapped to Read Committed, meaning it does not allow a transaction to see uncommitted data from other transactions.

**B09B.** PostgreSQL uses the Read Committed isolation level by default. This means that PostgreSQL's Read Uncommitted mode is not truly Read Uncommitted but rather behaves like Read Committed. As a result, PostgreSQL does not fully support the Read Uncommitted isolation level in the traditional sense.

**B09C.** PostgreSQL uses the Read Committed isolation level by default. It does not fully support the Read Uncommitted isolation level as defined in the standard; instead, PostgreSQL's Read Uncommitted mode behaves internally like Read Committed.


---

## B10. How many columns can a SQLite table have?

**Documentation:**

> [SQLite, Limits In SQLite, 3. Maximum Number Of Columns]
> The default setting for SQLITE_MAX_COLUMN is 2000. You can change it at compile time to values as large as 32767. On the other hand, many experienced database designers will argue that a well-normalized database will never need more than 100 columns in a table.

**B10A.** By default, a SQLite table can have up to 2000 columns. However, this limit can be increased to a maximum of 32767 by compiling SQLite with a higher SQLITE_MAX_COLUMN value, though this is not the default setting.


---

## B11. What happens if a Dockerfile has two CMD instructions?

**Documentation:**

> [Docker documentation, Dockerfile reference, CMD]
> There can only be one CMD instruction in a Dockerfile. If you list more than one CMD, only the last one takes effect.

**B11A.** If a Dockerfile has two CMD instructions, only the last one takes effect.


---

## B12. Can I use SQLite in WAL mode on a network file share?

**Documentation:**

> [SQLite, Write-Ahead Logging, 2. How WAL Works (disadvantages)]
> All processes using a database must be on the same host computer; WAL does not work over a network filesystem. This is because WAL requires all processes to share a small amount of memory and processes on separate host machines obviously cannot share memory with each other.

**B12A.** No, you cannot use SQLite in WAL mode on a network file share. WAL mode requires all processes to be on the same host computer and does not work over a network filesystem due to the requirement for shared memory that cannot be achieved between processes on separate host machines.

**B12B.** No, you cannot use SQLite in WAL mode on a network file share. WAL mode requires all processes to be on the same host computer because it relies on shared memory, which cannot be shared between processes on separate host machines.


---

## B13. Does a Python dict keep insertion order, and since which version is that guaranteed?

**Documentation:**

> [Python 3 documentation, Built-in Types, Mapping Types — dict]
> Changed in version 3.7: Dictionary order is guaranteed to be insertion order. This behavior was an implementation detail of CPython from 3.6.

**B13A.** Yes, a Python dict keeps insertion order, and as of Python 3.7, this order is guaranteed. In Python 3.6 and earlier, this behavior was an implementation detail and not guaranteed.


---

## B14. What does round(2.5) return in Python?

**Documentation:**

> [Python 3 documentation, Built-in Functions, round()]
> For the built-in types supporting round(), values are rounded to the closest multiple of 10 to the power minus ndigits; if two multiples are equally close, rounding is done toward the even choice (so, for example, both round(0.5) and round(-0.5) are 0, and round(1.5) is 2). Any integer value is valid for ndigits (positive, zero, or negative). The return value is an integer if ndigits is omitted or None.

**B14A.** In Python, round(2.5) returns 2. The documentation states that if two multiples are equally close, rounding is done toward the even choice. Therefore, both 2.5 and 3.5 would be rounded to 2 and 4, respectively, to maintain an even number at the given ndigits place.

**B14B.** I cannot state this point reliably from the documentation provided. According to the rounding rules described, when ndigits is omitted, the function should round to the nearest integer. However, the specific rule for halfway cases (like 2.5) is that it rounds to the nearest even number. I cannot state this point reliably from the documentation provided.

**B14C.** I cannot state this point reliably from the documentation provided. The documentation mentions that both `round(0.5)` and `round(-0.5)` are rounded to 0, implying a rounding rule towards the even choice. I cannot state this point reliably from the documentation provided. I cannot state this point reliably from the documentation provided.


---

## B15. Why does a Python function with a list as a default argument keep values between calls?

**Documentation:**

> [Python 3 documentation, Language Reference, 8.7 Function definitions]
> Default parameter values are evaluated from left to right when the function definition is executed. This means that the expression is evaluated once, when the function is defined, and that the same “pre-computed” value is used for each call. This is especially important to understand when a default parameter value is a mutable object, such as a list or a dictionary: if the function modifies the object (e.g. by appending an item to a list), the default parameter value is in effect modified. This is generally not what was intended. A way around this is to use None as the default, and explicitly test for it in the body of the function

**B15A.** A Python function with a list as a default argument keeps values between calls because the list is evaluated only once, at the time the function is defined. Subsequent calls to the function reuse the same pre-computed list, including any modifications made to it in previous calls. This is due to the way default parameter values are handled in Python, where they are evaluated at function definition time, not at each function call.

**B15B.** A Python function with a list as a default argument keeps values between calls because the list is evaluated only once, at the time the function is defined. Subsequent calls to the function reuse the same pre-computed list, including any modifications made to it in previous calls. This is due to the way default parameter values are handled in Python, where they are evaluated at function definition time, not each time the function is called.


---

## B16. What is the default restart policy of a Kubernetes Pod?

**Documentation:**

> [Kubernetes documentation, Pod Lifecycle, Container restart policy]
> The spec of a Pod has a restartPolicy field with possible values Always, OnFailure, and Never. The default value is Always.

**B16A.** The default restart policy of a Kubernetes Pod is Always.


---

## B17. What does pandas DataFrame.std divide by by default?

**Documentation:**

> [pandas documentation, pandas.DataFrame.std]
> Normalized by N-1 by default. This can be changed using the ddof argument.
>
> [pandas documentation, pandas.DataFrame.std, parameter ddof]
> Delta Degrees of Freedom. The divisor used in calculations is N - ddof, where N represents the number of elements.

**B17A.** By default, pandas DataFrame.std divides by N-1, where N is the number of elements.


---

## B18. When a server answers with HTTP 429, what should the response include?

**Documentation:**

> [RFC 6585, section 4 (429 Too Many Requests)]
> The 429 status code indicates that the user has sent too many requests in a given amount of time ("rate limiting").
>
> The response representations SHOULD include details explaining the condition, and MAY include a Retry-After header indicating how long to wait before making a new request.

**B18A.** When a server answers with HTTP 429, the response SHOULD include details explaining the condition of "too many requests in a given amount of time." The response MAY include a Retry-After header indicating how long to wait before making a new request.


---

## B19. What happens when a Kubernetes readiness probe fails, compared with a liveness probe?

**Documentation:**

> [Kubernetes documentation, Liveness, Readiness, and Startup Probes, Liveness probe]
> If a container fails its liveness probe more times than the configured tolerance, the kubelet restarts that container. Liveness probes do not wait for readiness probes to succeed.
>
> [Kubernetes documentation, Liveness, Readiness, and Startup Probes, Readiness probe]
> If the readiness probe returns a failed state, the EndpointSlice controller removes the Pod's IP address from the EndpointSlices of all Services that match the Pod.

**B19A.** When a Kubernetes readiness probe fails, the Pod's IP address is removed from the EndpointSlices of all matching Services. In contrast, if a liveness probe fails more times than the configured tolerance, the kubelet restarts the container without waiting for the readiness probe to succeed.


---

## B20. What are the default rolling update settings of a Kubernetes Deployment?

**Documentation:**

> [Kubernetes documentation, Deployments, Max Unavailable]
> .spec.strategy.rollingUpdate.maxUnavailable is an optional field that specifies the maximum number of Pods that can be unavailable during the update process. The value can be an absolute number (for example, 5) or a percentage of desired Pods (for example, 10%). The absolute number is calculated from percentage by rounding down. The value cannot be 0 if .spec.strategy.rollingUpdate.maxSurge is 0. The default value is 25%.
>
> [Kubernetes documentation, Deployments, Max Surge]
> .spec.strategy.rollingUpdate.maxSurge is an optional field that specifies the maximum number of Pods that can be created over the desired number of Pods. The value can be an absolute number (for example, 5) or a percentage of desired Pods (for example, 10%). The value cannot be 0 if maxUnavailable is 0. The absolute number is calculated from the percentage by rounding up. The default value is 25%.

**B20A.** The default rolling update settings for a Kubernetes Deployment are that .spec.strategy.rollingUpdate.maxUnavailable is 25% and .spec.strategy.rollingUpdate.maxSurge is 25%.


---

## B21. How should a JWT's exp claim be checked, and is any clock skew allowed?

**Documentation:**

> [RFC 7519, section 4.1.4 ("exp" (Expiration Time) Claim)]
> The "exp" (expiration time) claim identifies the expiration time on or after which the JWT MUST NOT be accepted for processing. The processing of the "exp" claim requires that the current date/time MUST be before the expiration date/time listed in the "exp" claim.
>
> Implementers MAY provide for some small leeway, usually no more than a few minutes, to account for clock skew. Its value MUST be a number containing a NumericDate value. Use of this claim is OPTIONAL.

**B21A.** I cannot state this point reliably from the documentation provided. However, based on the information given, the "exp" (expiration time) claim in a JWT should be checked to ensure that the current date/time is before the expiration date/time listed in the "exp" claim. Clock skew, which refers to the difference between the system clock and the actual time, is allowed, but implementers are advised to allow for only a small leeway, usually no more than a few minutes.

**B21B.** The "exp" (expiration time) claim in a JWT should be checked to ensure that the current date/time is before the expiration date/time specified in the "exp" claim. Implementers may allow for a small leeway, usually no more than a few minutes, to account for clock skew. However, the use of this claim is optional.

**B21C.** I cannot state this point reliably from the documentation provided. According to the documentation, implementers MAY allow for a small leeway, usually no more than a few minutes, to account for clock skew. However, the exact amount of leeway is not specified and is left to the implementer's discretion.


---

## B22. What regularisation does scikit-learn's LogisticRegression use by default?

**Documentation:**

> [scikit-learn documentation, sklearn.linear_model.LogisticRegression, parameter penalty]
> 'l2': add an L2 penalty term and it is the default choice;
>
> Deprecated since version 1.8: penalty was deprecated in version 1.8 and will be removed in 1.10. Use l1_ratio and C instead.
>
> [scikit-learn documentation, sklearn.linear_model.LogisticRegression, parameter C]
> Inverse of regularization strength; must be a positive float. Like in support vector machines, smaller values specify stronger regularization. C=np.inf results in unpenalized logistic regression.

**B22A.** By default, scikit-learn's LogisticRegression uses an L2 penalty term, which is specified by the parameter `penalty='l2'`. However, note that the `penalty` parameter is deprecated since version 1.8 and will be removed in version 1.10. Instead, you should use the `l1_ratio` and `C` parameters to control regularization.

**B22B.** By default, scikit-learn's LogisticRegression uses an L2 penalty term, which is specified by the parameter `penalty='l2'`. However, note that the `penalty` parameter is deprecated since version 1.8 and will be removed in version 1.10. By default, scikit-learn's LogisticRegression uses an L2 penalty term, which is specified by the parameter `penalty='l2'`. However, the `penalty` parameter is deprecated since version 1.8 and will be removed in version 1.10. Instead, you should use the `l1_ratio` and `C` parameters to control regularization.

**B22C.** By default, scikit-learn's LogisticRegression uses an L2 penalty term, which is specified by the parameter `penalty='l2'`. However, note that the `penalty` parameter is deprecated since version 1.8 and will be removed in version 1.10. Users are advised to use `l1_ratio` and `C` instead for specifying the type and strength of regularization.


---

## B23. Is TLS 1.3 0-RTT early data protected against replay?

**Documentation:**

> [RFC 8446, section 2.3 (0-RTT Data)]
> When clients and servers share a PSK (either obtained externally or via a previous handshake), TLS 1.3 allows clients to send data on the first flight ("early data"). The client uses the PSK to authenticate the server and to encrypt the early data.
>
> IMPORTANT NOTE: The security properties for 0-RTT data are weaker than those for other kinds of TLS data. Specifically:
>
> 1. This data is not forward secret, as it is encrypted solely under keys derived using the offered PSK.
>
> 2. There are no guarantees of non-replay between connections. Protection against replay for ordinary TLS 1.3 1-RTT data is provided via the server's Random value, but 0-RTT data does not depend on the ServerHello and therefore has weaker guarantees.
>
> 0-RTT data cannot be duplicated within a connection (i.e., the server will not process the same data twice for the same connection), and an attacker will not be able to make 0-RTT data appear to be 1-RTT data (because it is protected with different keys).

**B23A.** TLS 1.3 0-RTT early data does not have guarantees of non-replay between connections. The protection against replay for ordinary TLS 1.3 1-RTT data is provided via the server's Random value, but 0-RTT data does not depend on the ServerHello and therefore has weaker replay protection.


---

## B24. Does VACUUM FULL in PostgreSQL block other sessions from using the table?

**Documentation:**

> [PostgreSQL 17 documentation, VACUUM, parameter FULL]
> Selects “full” vacuum, which can reclaim more space, but takes much longer and exclusively locks the table. This method also requires extra disk space, since it writes a new copy of the table and doesn't release the old copy until the operation is complete. Usually this should only be used when a significant amount of space needs to be reclaimed from within the table.

**B24A.** Yes, VACUUM FULL in PostgreSQL exclusively locks the table, which blocks other sessions from using the table during the operation.


---

## B25. If I fix the random seed, are PyTorch results reproducible across CPU and GPU?

**Documentation:**

> [PyTorch 2.7 documentation, Reproducibility]
> Completely reproducible results are not guaranteed across PyTorch releases, individual commits, or different platforms. Furthermore, results may not be reproducible between CPU and GPU executions, even when using identical seeds.

**B25A.** Fixing the random seed does not guarantee that PyTorch results will be reproducible across CPU and GPU executions. According to the documentation, results may not be reproducible between CPU and GPU even when using identical seeds.

**B25B.** Fixing the random seed does not guarantee that PyTorch results will be reproducible across CPU and GPU executions. The documentation explicitly states that results may not be reproducible between CPU and GPU even when using identical seeds.

**B25C.** Fixing the random seed does not guarantee that PyTorch results will be reproducible across CPU and GPU executions. Completely reproducible results are not guaranteed even when using identical seeds for CPU and GPU executions.


---

## B26. A cookie has both Max-Age and Expires. Which one decides when it expires?

**Documentation:**

> [RFC 6265, section 4.1.2.2 (The Max-Age Attribute)]
> The Max-Age attribute indicates the maximum lifetime of the cookie, represented as the number of seconds until the cookie expires. The user agent is not required to retain the cookie for the specified duration.
>
> If a cookie has both the Max-Age and the Expires attribute, the Max-Age attribute has precedence and controls the expiration date of the cookie. If a cookie has neither the Max-Age nor the Expires attribute, the user agent will retain the cookie until "the current session is over" (as defined by the user agent).

**B26A.** If a cookie has both the Max-Age and the Expires attributes, the Max-Age attribute has precedence and controls the expiration date of the cookie.


---

## B27. What happens on integer overflow in Rust?

**Documentation:**

> [The Rust Programming Language, 3.2 Data Types, Integer Overflow]
> When you’re compiling in debug mode, Rust includes checks for integer overflow that cause your program to panic at runtime if this behavior occurs.
>
> When you’re compiling in release mode with the --release flag, Rust does not include checks for integer overflow that cause panics. Instead, if overflow occurs, Rust performs two’s complement wrapping. In short, values greater than the maximum value the type can hold “wrap around” to the minimum of the values the type can hold. In the case of a u8, the value 256 becomes 0, the value 257 becomes 1, and so on. The program won’t panic, but the variable will have a value that probably isn’t what you were expecting it to have. Relying on integer overflow’s wrapping behavior is considered an error.

**B27A.** In Rust, the behavior of integer overflow depends on the compilation mode. In debug mode, Rust includes checks that will cause your program to panic at runtime if an overflow occurs. However, in release mode with the --release flag, Rust does not include these checks. Instead, it performs two’s complement wrapping, meaning that values exceeding the maximum value for the type "wrap around" to the minimum value. For example, a u8 overflow would cause 256 to become 0, 257 to become 1, and so on. This behavior is considered an error and should be avoided.


---

## B28. If a server returns 301 for a POST request, can the browser switch to GET, and how do you prevent that?

**Documentation:**

> [RFC 9110, section 15.4.2 (301 Moved Permanently)]
> The 301 (Moved Permanently) status code indicates that the target resource has been assigned a new permanent URI and any future references to this resource ought to use one of the enclosed URIs.
>
> For historical reasons, a user agent MAY change the request method from POST to GET for the subsequent request. If this behavior is undesired, the 308 (Permanent Redirect) status code can be used instead.

**B28A.** If a server returns a 301 (Moved Permanently) for a POST request, the browser MAY switch the request method from POST to GET for the subsequent request. To prevent this behavior, the server should use the 308 (Permanent Redirect) status code instead of 301.


---

## B29. Which HTTP methods are idempotent, and when can a client retry a request automatically?

**Documentation:**

> [RFC 9110, section 9.2.2 (Idempotent Methods)]
> A request method is considered "idempotent" if the intended effect on the server of multiple identical requests with that method is the same as the effect for a single such request. Of the request methods defined by this specification, PUT, DELETE, and safe request methods are idempotent.
>
> Idempotent methods are distinguished because the request can be repeated automatically if a communication failure occurs before the client is able to read the server's response.
>
> A client SHOULD NOT automatically retry a request with a non-idempotent method unless it has some means to know that the request semantics are actually idempotent, regardless of the method, or some means to detect that the original request was never applied.

**B29A.** The HTTP methods PUT, DELETE, and the "safe" request methods are idempotent. A client SHOULD NOT automatically retry a request with a non-idempotent method unless it has a way to confirm that the request semantics are idempotent or can detect that the original request was not applied.


---

## B30. In Kubernetes, what happens when a container goes over its CPU limit, and over its memory limit?

**Documentation:**

> [Kubernetes documentation, Resource Management for Pods and Containers, How Kubernetes applies resource requests and limits]
> cpu limits are enforced by CPU throttling. When a container approaches its cpu limit, the kernel will restrict access to the CPU corresponding to the container's limit. Thus, a cpu limit is a hard limit the kernel enforces. Containers may not use more CPU than is specified in their cpu limit.
>
> memory limits are enforced by the kernel with out of memory (OOM) kills. When a container uses more than its memory limit, the kernel may terminate it. However, terminations only happen when the kernel detects memory pressure. Thus, a container that over allocates memory may not be immediately killed. This means memory limits are enforced reactively. A container may use more memory than its memory limit, but if it does, it may get killed.

**B30A.** When a container goes over its CPU limit in Kubernetes, the kernel enforces the limit by throttling the CPU access. The container will not be able to use more CPU than specified in its limit.

For memory limits, if a container exceeds its allocated memory, the kernel may terminate the container if it detects memory pressure. However, this termination is not immediate; it depends on the overall system memory situation. Therefore, a container can temporarily use more memory than its limit, but if it does, it risks being terminated by the kernel.


---

## B31. Can I run CREATE INDEX CONCURRENTLY inside a transaction in PostgreSQL, and what does it avoid?

**Documentation:**

> [PostgreSQL 17 documentation, CREATE INDEX, parameter CONCURRENTLY]
> When this option is used, PostgreSQL will build the index without taking any locks that prevent concurrent inserts, updates, or deletes on the table; whereas a standard index build locks out writes (but not reads) on the table until it's done.
>
> [PostgreSQL 17 documentation, CREATE INDEX, Building Indexes Concurrently]
> Another difference is that a regular CREATE INDEX command can be performed within a transaction block, but CREATE INDEX CONCURRENTLY cannot.

**B31A.** No, you cannot run CREATE INDEX CONCURRENTLY inside a transaction in PostgreSQL. CREATE INDEX CONCURRENTLY avoids locking out writes (inserts, updates, or deletes) on the table while the index is being built, which a standard CREATE INDEX command would do.


---

## B32. What is the maximum length of a table name in PostgreSQL?

**Documentation:**

> [PostgreSQL 17 documentation, 4.1.1 Identifiers and Key Words]
> The system uses no more than NAMEDATALEN-1 bytes of an identifier; longer names can be written in commands, but they will be truncated. By default, NAMEDATALEN is 64 so the maximum identifier length is 63 bytes. If this limit is problematic, it can be raised by changing the NAMEDATALEN constant in src/include/pg_config_manual.h.

**B32A.** The maximum length of a table name in PostgreSQL is 63 bytes. This is because the system uses no more than NAMEDATALEN-1 bytes of an identifier, and by default, NAMEDATALEN is set to 64.


---

## B33. What is the largest integer JavaScript can represent exactly?

**Documentation:**

> [MDN Web Docs, Number.MAX_SAFE_INTEGER]
> The Number.MAX_SAFE_INTEGER static data property represents the maximum safe integer in JavaScript (2^53 – 1).
>
> Double precision floating point format only has 52 bits to represent the mantissa, so it can only safely represent integers between -(2^53 – 1) and 2^53 – 1. "Safe" in this context refers to the ability to represent integers exactly and to compare them correctly. For example, Number.MAX_SAFE_INTEGER + 1 === Number.MAX_SAFE_INTEGER + 2 will evaluate to true, which is mathematically incorrect.

**B33A.** The largest integer JavaScript can represent exactly is 2^53 – 1, which is the value of Number.MAX_SAFE_INTEGER.


---

## B34. What share of the data goes to the test set in scikit-learn's train_test_split by default?

**Documentation:**

> [scikit-learn documentation, sklearn.model_selection.train_test_split, parameter test_size]
> If float, should be between 0.0 and 1.0 and represent the proportion of the dataset to include in the test split. If int, represents the absolute number of test samples. If None, the value is set to the complement of the train size. If train_size is also None, it will be set to 0.25.

**B34A.** If `test_size` is `None`, the value is set to the complement of the `train_size`. If both `train_size` and `test_size` are `None`, `test_size` will be set to 0.25.

**B34B.** By default, 25% of the data goes to the test set in scikit-learn's train_test_split when the test_size parameter is not specified.

**B34C.** I cannot state this point reliably from the documentation provided. The documentation indicates that if `test_size` is a float, it should be between 0.0 and 1.0 and represents the proportion of the dataset to include in the test split. However, it does not specify the default value for `test_size`. The default value for `test_size` is not documented in the snippet provided.


---

## B35. What does optimizer.zero_grad() do to the gradients by default in PyTorch?

**Documentation:**

> [PyTorch 2.7 documentation, torch.optim.Optimizer.zero_grad]
> Optimizer.zero_grad(set_to_none=True)
>
> set_to_none (bool) – instead of setting to zero, set the grads to None. This will in general have lower memory footprint, and can modestly improve performance. However, it changes certain behaviors.

**B35A.** By default, `optimizer.zero_grad()` in PyTorch sets the gradients to zero. However, the specific behavior can be controlled by the `set_to_none` parameter. When `set_to_none` is `False` (the default), the gradients are set to zero.


---

## B36. What happens in Go if you write to a nil map?

**Documentation:**

> [The Go Programming Language Specification, Map types]
> A nil map is equivalent to an empty map except that no elements may be added.
>
> [The Go Programming Language Specification, Index expressions]
> Assigning to an element of a nil map causes a run-time panic.

**B36A.** If you write to a nil map in Go, a run-time panic will occur.


---

## B37. What divisor does numpy.std use by default?

**Documentation:**

> [NumPy documentation, numpy.std, parameter ddof]
> Means Delta Degrees of Freedom. The divisor used in calculations is N - ddof, where N represents the number of elements. By default ddof is zero.

**B37A.** By default, numpy.std uses a divisor of N, where N is the number of elements. This is because the default value of ddof is zero.

**B37B.** I cannot state this point reliably from the documentation provided. The documentation indicates that the default value for ddof is zero, but it does not explicitly state the divisor used by default. Given ddof = 0, the divisor used by default in numpy.std calculations is N, where N is the number of elements.

**B37C.** I cannot state this point reliably from the documentation provided. The documentation specifies that the default value for `ddof` is zero, but it does not explicitly state the divisor used by default by `numpy.std`. Given `ddof=0`, the divisor used by default is \( N \), where \( N \) is the number of elements.


---

## B38. Can a Prometheus counter go down?

**Documentation:**

> [Prometheus documentation, Metric types, Counter]
> A counter is a cumulative metric that represents a single monotonically increasing counter whose value can only increase or be reset to zero on restart. For example, you can use a counter to represent the number of requests served, tasks completed, or errors.
>
> Do not use a counter to expose a value that can decrease. For example, do not use a counter for the number of currently running processes; instead use a gauge.

**B38A.** A Prometheus counter cannot go down. It is designed to represent a single monotonically increasing metric that can only increase or be reset to zero on restart. Therefore, a counter in Prometheus will not go down.

**B38B.** No, a Prometheus counter cannot go down. It is designed to represent a single monotonically increasing metric that can only increase or be reset to zero on restart.

**B38C.** A Prometheus counter cannot go down. It is designed to represent a single monotonically increasing counter whose value can only increase or be reset to zero on restart. Therefore, a counter should not be used to expose a value that can decrease; for that, a gauge should be used instead.


---

## B39. Do WebSocket frames have to be masked, and in which direction?

**Documentation:**

> [RFC 6455, section 5.1 (Overview)]
> To avoid confusing network intermediaries (such as intercepting proxies) and for security reasons that are further discussed in Section 10.3, a client MUST mask all frames that it sends to the server (see Section 5.3 for further details). (Note that masking is done whether or not the WebSocket Protocol is running over TLS.) The server MUST close the connection upon receiving a frame that is not masked. In this case, a server MAY send a Close frame with a status code of 1002 (protocol error) as defined in Section 7.4.1. A server MUST NOT mask any frames that it sends to the client. A client MUST close a connection if it detects a masked frame.

**B39A.** WebSocket frames must be masked when sent from a client to a server, but not when sent from a server to a client.

**B39B.** I cannot state this point reliably from the documentation provided. I cannot state this point reliably from the documentation provided. I cannot state this point reliably from the documentation provided.

**B39C.** I cannot state this point reliably from the documentation provided. The documentation specifies that a client MUST mask all frames it sends to the server, and a server MUST NOT mask any frames it sends to the client. I cannot state this point reliably from the documentation provided.


---

## B40. Is the iteration order of a Go map in a for range loop stable?

**Documentation:**

> [The Go Programming Language Specification, For statements with range clause]
> The iteration order over maps is not specified and is not guaranteed to be the same from one iteration to the next. If a map entry that has not yet been reached is removed during iteration, the corresponding iteration value will not be produced. If a map entry is created during iteration, that entry may be produced during the iteration or may be skipped.

**B40A.** No, the iteration order of a Go map in a for range loop is not stable and is not guaranteed to be the same from one iteration to the next.

