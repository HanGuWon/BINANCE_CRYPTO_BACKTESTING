# Model artifact verification

Evaluation must recompute the model artifact SHA256 from bytes and verify the
predictability-v1-model-v1 schema plus campaign, training-cutoff, feature, and
lineage metadata. Any mismatch is a hard error before scoring; outcomes remain
NOT_RUN and final_holdout remains UNTOUCHED.
