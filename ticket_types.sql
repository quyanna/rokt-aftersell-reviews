-- Ticket types for the triage sheet, derived from the classifier's fields by
-- rules rather than by asking the model for a label.
--
-- Why: the model reliably sets support_failure but would not use the
-- "support_only" category, reading the name too literally when a review also
-- mentioned a chatbot or a named agent. That left 14 support complaints sitting
-- in "other". A rule fixes it deterministically, and unlike a model judgement it
-- can be read, argued with, and re-run to the same answer.
--
-- Order matters: the first matching branch wins.

CREATE VIEW IF NOT EXISTS ticket_types AS
SELECT
    c.review_id,
    r.app,
    r.rating,
    r.tenure_bucket,
    c.resolvability,
    c.evidence_quote,
    c.confidence,
    CASE
        -- A named fault always beats the support experience around it. A merchant
        -- whose billing broke AND who waited three days is a billing ticket.
        WHEN c.complaint_type NOT IN ('other', 'support_only') THEN c.complaint_type
        -- No named fault, but support was the problem. This is the branch that
        -- rescues the reviews the model filed under "other".
        WHEN c.support_failure = 1 THEN 'support_experience'
        ELSE 'unclassified'
    END AS ticket_type
FROM classifications c
JOIN reviews r USING (review_id)
WHERE c.complaint_type IS NOT NULL;
