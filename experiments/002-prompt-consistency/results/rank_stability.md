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

