# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | Yes |
| < 0.1 | No |

## Reporting a vulnerability

Please report suspected vulnerabilities privately to **abdullah@memonsystems.com**
with the subject line `legal-rag-verifier security`. Do not open a public issue.

Include the affected version, a description of the issue, and, where possible, a minimal
reproduction. You will receive an acknowledgement within 3 working days and a status update
within 10 working days.

## Scope notes

- The core package makes no network calls. `SGLangBackend` sends HTTP requests only to the
  server URL it is given. Any way for answer or premise text to change the request target or
  inject server-side options is in scope.
- The `allow` and `ban` retry modes send a logit processor to the SGLang server, which must run
  with `--enable-custom-logit-processor`. That flag lets clients run code on the server: expose
  such a server only to trusted clients. Ways for answer or premise text to alter the processor
  sent are in scope.
- The NLI head and the Hugging Face backend load model weights through `transformers`. Loading
  untrusted weights is out of scope; pin the model revision you trust.
- Pathological inputs that make the claim check exceed its latency budget (for example regular
  expression backtracking) are in scope.
