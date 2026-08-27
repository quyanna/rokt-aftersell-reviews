# How resolvability is worded in the report

The database stores three values. The report shows different wording, for a reason
recorded here rather than left as an unexplained rename.

| Stored value | Shown as | Means |
|---|---|---|
| `support_can_fix` | Support resolves it | An agent with admin access, willing to change settings or write CSS, closes this in the ticket. Refunds and credits count. |
| `explain_only` | Support explains it | Nothing is broken. A Shopify platform rule, the pricing model working as documented, or a feature that genuinely does not exist. |
| `needs_engineering` | Support triages, engineering fixes | Support still takes first contact, reproduces the fault and gathers evidence. Resolution needs an engineer. |
| `cannot_tell` | Not decidable from the review | The review does not say enough to choose between the three above. |

## Why the third one was reworded

The hand-audit on 26 August 2026 disagreed with exactly one of 41 sampled reviews.
The review was "Discount codes wont work, sort of like their non existent customer
support", labelled `needs_engineering`. The auditor's position was that support
could reproduce and explain the issue, escalating only if that turned out to be
necessary.

That is right, and it is right about all 31 rows carrying the label, not just the
one. **Support takes first contact on every ticket in this dataset regardless of
category.** A label reading "needs engineering" implies support does nothing, which
is not how any support queue works, and it makes the escalation figure sound like a
hand-off rate when it is really a "cannot be closed by support alone" rate.

The stored value is unchanged, so the audit trail and the model's own reasoning stay
intact. Only the wording a reader sees is different, and this file records that the
change came from the audit rather than from tidying.
