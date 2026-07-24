# Exploratory: rank stability of first-mention brand order

Kendall's tau over shared brands (>= 3), prompt-cluster
bootstrap 90% CIs (n_boot=2000, seed=20260716). NOT pre-registered;
computed post-publication in response to a reader question.

## Same prompt, repeated runs
- pairs with >= 3 shared brands: 2468/3003 (82%); mean shared 3.44
- mean Kendall tau = +0.644 [+0.615, +0.673]
- perfect agreement (tau=1): 46.2%; zero-or-negative: 12.0%; full reversal: 0.9%
- same first-mentioned brand: 68.3% [65.4%, 71.1%]

## Different prompts, same intent
- pairs with >= 3 shared brands: 49594/71071 (70%); mean shared 2.82
- mean Kendall tau = +0.358 [+0.311, +0.410]
- perfect agreement (tau=1): 31.2%; zero-or-negative: 31.9%; full reversal: 5.2%
- same first-mentioned brand: 39.7% [36.0%, 43.7%]

## Chance baseline
- top-slot agreement from the empirical first-brand mix: 39.9%
- most common opener: sony (59.9% of answers)

## Robustness checks (reader-raised selection concerns)

- Same prompt, repeated runs: excluded pairs with exactly 2 shared brands (n=238) are concordant 76.1% (chance 50%) — less ordered than included pairs, not chaotic; mean tau by shared-set size {3: 0.601, 4: 0.654, 5: 0.698, 6: 0.623, 7: 0.635, 8: 0.554}
- Different prompts, same intent: excluded pairs with exactly 2 shared brands (n=7642) are concordant 59.4% (chance 50%) — less ordered than included pairs, not chaotic; mean tau by shared-set size {3: 0.271, 4: 0.417, 5: 0.473, 6: 0.416, 7: 0.471, 8: 0.0}
- within-prompt zero-or-negative pairs (295) are spread across 63 prompts; prompts whose MEAN within-prompt tau <= 0: 2 of 136; per-prompt mean tau 10th pct +0.22, median +0.68

