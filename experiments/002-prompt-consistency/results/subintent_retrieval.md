# Exploratory: sub-intent convergence in the retrieval layer

Same-wave between-prompt pairs, split per attribute into both/mixed/
neither. Values are mean pairwise Jaccard; Δ rows are cluster-bootstrap
contrasts (90% CI, n_boot=2000, seed=20260716). NOT pre-registered.

## Specific dollar budget
- brands: both 0.370 / mixed 0.432 / neither 0.583; Δ(both−mixed) = -0.062 [-0.108, -0.009] *
- grounding_tokens: both 0.220 / mixed 0.187 / neither 0.269; Δ(both−mixed) = +0.033 [+0.003, +0.065] *
- domains: both 0.291 / mixed 0.277 / neither 0.306; Δ(both−mixed) = +0.014 [-0.034, +0.068] 

## Named gift recipient
- brands: both 0.417 / mixed 0.484 / neither 0.560; Δ(both−mixed) = -0.068 [-0.113, -0.017] *
- grounding_tokens: both 0.177 / mixed 0.213 / neither 0.259; Δ(both−mixed) = -0.037 [-0.055, -0.013] *
- domains: both 0.254 / mixed 0.281 / neither 0.305; Δ(both−mixed) = -0.027 [-0.072, +0.032] 

## Music usage
- brands: both 0.589 / mixed 0.495 / neither 0.417; Δ(both−mixed) = +0.094 [+0.034, +0.165] *
- grounding_tokens: both 0.253 / mixed 0.238 / neither 0.238; Δ(both−mixed) = +0.015 [-0.014, +0.046] 
- domains: both 0.319 / mixed 0.280 / neither 0.249; Δ(both−mixed) = +0.039 [+0.004, +0.078] *

## Travel context
- brands: both 0.577 / mixed 0.467 / neither 0.381; Δ(both−mixed) = +0.110 [+0.039, +0.193] *
- grounding_tokens: both 0.292 / mixed 0.158 / neither 0.144; Δ(both−mixed) = +0.134 [+0.100, +0.170] *
- domains: both 0.331 / mixed 0.238 / neither 0.193; Δ(both−mixed) = +0.093 [+0.047, +0.139] *

## Noise-cancelling
- brands: both 0.559 / mixed 0.546 / neither 0.531; Δ(both−mixed) = +0.013 [-0.038, +0.069] 
- grounding_tokens: both 0.295 / mixed 0.239 / neither 0.246; Δ(both−mixed) = +0.056 [+0.012, +0.106] *
- domains: both 0.313 / mixed 0.302 / neither 0.294; Δ(both−mixed) = +0.011 [-0.023, +0.047] 

## Form factor
- brands: both 0.359 / mixed 0.444 / neither 0.563; Δ(both−mixed) = -0.085 [-0.139, -0.016] *
- grounding_tokens: both 0.189 / mixed 0.206 / neither 0.256; Δ(both−mixed) = -0.017 [-0.049, +0.025] 
- domains: both 0.235 / mixed 0.262 / neither 0.308; Δ(both−mixed) = -0.027 [-0.068, +0.022] 

## Budget-bucket check (valued-attribute mechanism)
Among the 23 budget prompts with a parseable amount (range 50-500), split at 150:
- same-bucket brand Jaccard 0.452 vs different-bucket 0.285; Δ = +0.167 [+0.055, +0.294]
- i.e. the sub-intent unit is the attribute VALUE, not the flag: two prompts naming similar budgets converge; different budgets are different markets.

