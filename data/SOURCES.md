# Data Sources Evaluation

*Prepared 2026-10-01 for Rex (Verafy). **Status: PROPOSAL, awaiting approval (GATE G-002).** "Unverified" means it couldn't be confirmed from a primary source during this review. Nothing is ingested until Rex approves; approval is recorded by listing source keys in `data/approved_sources.txt`.*

## Summary

- **AVeriTeC fits our schema almost perfectly, but it is CC BY-NC 4.0.** Its 4 labels map one-to-one to ours. Its 2024 and 2025 test labels are hidden.
- **No existing dataset has claims dated after 2026-06.** The post-cutoff slice has to come from live ClaimReview data, with rationales we write ourselves.
- **The Google Fact Check Tools API terms forbid building a database from its content.** The Data Commons ClaimReview feed (CC BY, refreshed daily) is the licensable way to store items.
- **PolitiFact's terms forbid commercial use and building databases from its content.** This applies to LIAR, LIAR2 and LIAR-PLUS whatever license those repos state.
- **None of the debate corpora has a truth verdict.** They are left out of gold scoring.

## 0. Recommendation table

| # | Source | Label quality | License (commercial use by Verafy?) | Schema fit | Post-2026-06 items? | Contamination | Recommendation |
|---|---|---|---|---|---|---|---|
| 1 | **AVeriTeC** (2023) train/dev | Trained annotators, 5-phase QA; free-marginal κ 0.619 / Fleiss κ 0.503 | **CC BY-NC 4.0: NC** | Excellent | No (claims ≤ 2020-10) | High | **Dev, only if NC is accepted or the authors grant permission** |
| 1b | AVeriTeC 2024 / 2025 test sets | Same | CC BY-NC 4.0 | Same | No | Med | **Not usable: labels are hidden** |
| 2 | LIAR / LIAR-PLUS / LIAR2 | PolitiFact editors | Repo labels vary, **but PolitiFact content is © Poynter, non-commercial** | Good | No (LIAR2 ends 2023-07) | Very high | **Exclude from gold** |
| 2b | Google Fact Check Tools API | IFCN fact-checkers | Google APIs ToS: **no building databases or permanent copies** | Partial (no rationale) | **Yes** (live) | Lowest | **Discovery only** |
| 2c | Data Commons ClaimReview feed | Same as 2b | "CC BY" compilation (version unspecified); per-item `sdLicense` | Partial | **Yes** (daily) | Lowest | **Main stored source for the post-cutoff holdout** |
| 3 | FEVER | Crowd; synthetic Wikipedia mutations | CC BY-SA 3.0 | Weak | No | Very high | **Dev sanity baseline only (≤ 50 items)** |
| 4 | Debate sets (IQ2, args.me, DebateSum, CMV, Kialo, DDO) | Persuasion votes, not truth | Mixed / unspecified; Kialo forbids scraping | Poor | No | High | **Exclude from gold** |
| 5a | SciFact | Expert annotators | **Claims CC BY 4.0**; abstracts ODC-By | Medium | No | High | **Dev (license-clean)** |
| 5b | FACTors (2025) | 39 IFCN/EFCSN fact-checkers | **CC BY 4.0** (per paper) | Medium (no rationale) | No (1995–2025) | Med–high | **Dev + recent pre-cutoff holdout stratum** |
| 5c | QuanTemp | Fact-checkers (numeric claims) | CC BY-NC 4.0 | Good | No | Med | Optional, same NC caveat |
| 5d | Climate-FEVER | Crowd votes | Unverified | Medium | No | High | Hold |
| 5e | PubHealth | Fact-checker labels | MIT on HF, but contains Snopes/PolitiFact text | Good | No | High | Exclude |
| 5f | X-Fact | Fact-checkers, 25 languages | MIT (HF card) | Medium | No | Med | Later (multilingual) |
| 5g–l | MultiFC, ClaimDecomp, HealthVer, ClaimReview2024+, M4FC, TSVer | various | unverified / NC / PolitiFact upstream | — | No | — | Exclude or later |

## 1. AVeriTeC

Paper https://arxiv.org/abs/2305.13117 · https://fever.ai/dataset/averitec.html · https://github.com/MichSchli/AVeriTeC

- **Label quality:** 4,568 real-world claims from 50 fact-checking organizations. Annotators re-annotated each claim through 5 phases: claim normalization, question generation and answering, verdict plus justification, and a second QA round. Agreement: free-marginal κ = 0.619, Fleiss κ = 0.503. The verdict is the annotators' own, informed by the fact-check article.
- **License:** CC BY-NC 4.0, stated on both fever.ai and GitHub. Using it to benchmark protocols for a commercial product is arguably commercial. It is not cleared for Verafy unless the authors grant written permission.
- **Fit:** excellent. Uses `claim`, `speaker`, `claim_date` (DD-MM-YYYY), `label`, `fact_checking_article`, `justification` and `questions[]`. Ingester: `lab/data/ingest/averitec.py`.
- **Size and dates:** train 3,068 (claims to 2020-08-25); dev 500 (to 2020-10-31). Test-set labels are hidden. Labels: refuted 57–62%, supported 26–28%, conflicting 6–8%, NEE 6–9%.
- **Download:** https://huggingface.co/chenxwh/AVeriTeC/tree/main/data (`train.json`, `dev.json`).
- **Contamination:** high (public since 2023; events from 2020).

## 2. PolitiFact-derived sets and ClaimReview

- **LIAR** (HF `ucsbnlp/liar`): 12.8K statements in 6 classes; no date, URL or rationale; license unknown.
- **LIAR-PLUS** (github.com/Tariq60/LIAR-PLUS): TSV with justification. It shows a CC0 badge but says "research purposes only".
- **LIAR2** (github.com/chengxuphd/liar2): about 23K rows dated 2000-10 → 2023-07 with justification; declares Apache-2.0.
- **License problem shared by all three:** PolitiFact's terms (politifact.com/copyright) allow only "personal, non-commercial use". They prohibit "creating databases or archiving significant portions" and require Poynter's written consent for derivative works. A redistributor cannot relicense Poynter's text. **Exclude**, or request a license from editor@politifact.com.
- **Google Fact Check Tools API** (`claims:search`): returns `text`, `claimant`, `claimDate` and `claimReview[]` with `publisher`, `url`, `title`, `reviewDate` and `textualRating`. There is no rationale field.
  - The Google APIs ToS forbid "scrap[ing], build[ing] databases, or otherwise creat[ing] permanent copies" of the content. **Use it for discovery only.** Rate limits are unpublished (unverified).
  - In June 2025 Google removed ClaimReview rich snippets from Search, which may reduce how much markup publishers add in 2026. Smoke-test the volume first (§8).
- **Data Commons ClaimReview feed:** `https://storage.googleapis.com/datacommons-feeds/claimreview/latest/data.json`, schema.org DataFeed format, refreshed daily.
  - "Licensed under CC BY" (version unstated); per-item `sdLicense`; publishers keep the rights to their articles.
  - The FAQ says "academic research and innovation", which is ambiguous for commercial use.
  - It covers only markup created with Google's tools, so some publishers may be missing.
  - Ingester: `lab/data/ingest/datacommons.py`.
- **Duke Reporters' Lab, Fact-Check Insights:** more than 200K ClaimReview records; registration required; terms unverified. Worth applying as a coverage cross-check.

The existing `lab/data/ingest/liar.py` and `claimreview.py` (API-response format) are kept for tests and for use under a license, but they're off unless approved.

## 3. FEVER (sanity baseline)

- fever.ai/dataset/fever.html: 185K crowd-written mutations of Wikipedia sentences (2017 dump).
- License: CC BY-SA 3.0 / Wikipedia terms. Commercial use is allowed with attribution and share-alike.
- No speaker, date, URL or rationale; saturated. Use a 50-item dev sanity slice only. Items carry `crowd_labeled` and never enter the holdout.

## 4. Human-judged debates

| Dataset | Outcome label | License |
|---|---|---|
| IQ2 (ConvoKit `iq2-corpus`) | Audience pre/post votes | Corpus license unverified |
| CMV "Winning Arguments" | Δ awarded (persuasion) | Not specified; Reddit API terms |
| args.me | None (stance only) | CC BY 4.0 |
| DebateSum | None | MIT |
| Debate.org (DDO) | Voter-judged winners | Unverified |
| Kialo | Impact votes | Scraping forbidden |

None has a truth verdict that maps to our labels; audience votes measure persuasion, not truth. **Exclude debates from gold scoring.** The schema keeps `kind: debate` for a possible future "persuasion vs. truth" side benchmark.

## 5. Other claim sets

- **SciFact** (github.com/allenai/scifact):
  - License: claims and annotations CC BY 4.0; abstracts ODC-By 1.0.
  - About 1.4K expert-written scientific claims checked against abstracts.
  - Labels: SUPPORT / CONTRADICT, or empty evidence = NEI.
  - Files: `claims_{train,dev}.jsonl` (`id, claim, evidence{doc_id: [{sentences, label}]}, cited_doc_ids`) plus `corpus.jsonl`.
  - Ingester: `lab/data/ingest/scifact.py`.
- **FACTors** (github.com/altuncu/FACTors, arXiv 2505.09414):
  - License: CC BY 4.0 per the paper.
  - 118K English claims from 39 IFCN/EFCSN signatories, 1995–2025.
  - CSV with claim, original verdict, normalized rating, URL, date, organization.
  - Full report text was removed, so there's no rationale.
  - Ingester: `lab/data/ingest/factors.py`. Column names follow the paper; confirm them against the release before ingesting.
- **QuanTemp:** CC BY-NC 4.0; True/False/Conflicting; good fit, NC caveat.
- **Climate-FEVER:** license unverified.
- **PubHealth:** contains Snopes and PolitiFact text; exclude.
- **X-Fact:** MIT; multilingual later.
- **MultiFC, ClaimDecomp, HealthVer, ClaimReview2024+:** exclude.
- **M4FC:** CC BY-SA 4.0, multimodal; later.

## 6. Label mappings → {supported, refuted, not_enough_evidence, conflicting}

Every item keeps `source_label` (the original label) and `mapping` (`exact` | `lossy` | `manual`).

| Source | Mapping |
|---|---|
| AVeriTeC (exact) | Supported→supported · Refuted→refuted · Not Enough Evidence→NEE · Conflicting Evidence/Cherrypicking→conflicting |
| FEVER (exact, 3-way) | SUPPORTS→supported · REFUTES→refuted · NOT ENOUGH INFO→NEE |
| SciFact (claim level) | all SUPPORT→supported · all CONTRADICT→refuted · no evidence→NEE · mixed→conflicting (manual) |
| PolitiFact 6-way | true→supported · mostly-true→supported (lossy) · half-true→conflicting (lossy) · barely-true/mostly-false→refuted (lossy) · false/pants-fire→refuted |
| FACTors normalized | true→supported · partially true→conflicting (lossy) · false→refuted · misleading→conflicting (lossy) · unverifiable→NEE · other→drop |
| ClaimReview `textualRating` | true/correct/accurate/verified→supported; false/fake/incorrect/fabricated/hoax/pants on fire/four Pinocchios/altered/misattributed→refuted; mostly true/mostly false→lossy; half true/mixture/misleading/missing context/cherry-picked/partly false/exaggerated→conflicting; unproven/unverified/unsupported/insufficient evidence→NEE; "no evidence"→**manual** (often used for false claims); satire/explainer/opinion/outdated/unmatched→drop |

**Proposed holdout policy:** headline scores count only `exact` mappings and `manual` mappings a human has confirmed. `lossy` items are reported as a separate stratum.

## 7. Flags

- **`political`:** the speaker is an official, candidate, party, government body or campaign; or the topic is elections, legislation, policy, immigration, taxes, war or officials' records; or the source is PolitiFact, FactCheck.org or the WaPo Fact Checker. Ingesters set it by keyword and speaker heuristics. Human confirmation is planned for the post-cutoff set.
- **`named_person`:** the claim asserts something **about** an identifiable real person. Ingesters set it by heuristic (speaker field, capitalized name pairs), so it errs toward over-flagging, which is the safe direction for social posting. Flagged items are never auto-selected for posts (spec §9.2).

## 8. Plan to reach dev ≥ 300 and holdout ≥ 500

**Post-cutoff definition:** `review_date ≥ 2026-07-01`, and `claim_date ≥ 2026-06-15` when present, re-checked against each model's `knowledge_cutoff` in `config/models.yaml`.

**Post-cutoff pipeline (the holdout core):**
1. **Smoke test.** Query the Fact Check API per IFCN signatory (`reviewPublisherSiteFilter`, `maxAgeDays=95`) and count items in the Data Commons feed. Go/no-go: at least 600 candidates, allowing for about 50% attrition.
2. **Storage.** Store only Data Commons items or our own paraphrased records. API payloads are never stored as a corpus.
3. **Annotation** (about 6 minutes per item):
   - An annotator confirms the claim and date, applies the mapping and writes an original 1–3 sentence rationale.
   - 20% is double-labeled so we can report κ.
   - No panel model drafts rationales.
   - About 36 hours for 300 items.
4. **Weekly refresh.** The post-cutoff margin grows over time.

**Option A: license-clean (recommended default)**

| Split | Source | n |
|---|---|---|
| Dev | SciFact dev + train sample | 150 |
| Dev | FACTors 2018–2024 sample (+ in-house rationales) | 150 |
| Dev | FEVER | 50 |
| Holdout | Post-cutoff ClaimReview (≥ 2026-07-01) | ≥ 300 (headline) |
| Holdout | FACTors 2025 (recent, pre-cutoff) | 200 |

**Option B: if AVeriTeC's NC license is cleared.** Dev: AVeriTeC dev 300 + FEVER 50. Holdout: post-cutoff ClaimReview ≥ 300 + 200 frozen AVeriTeC train items.

Under either option, stratify so each of the 4 labels has at least 15% of the post-cutoff slice; natural data is about 60% refuted.

**Contamination controls:**
- Dedupe across splits and against public sets.
- Run a "verdict recall" probe asking each model, without retrieval, whether it knows the fact-check outcome, and report scores with and without the items it knew.
- Report pre-cutoff and post-cutoff strata separately.

## 9. Decisions for Rex (GATE G-002)

1. **AVeriTeC:** exclude, ask the authors for commercial-evaluation permission (recommended, running Option A meanwhile), or accept it as internal non-commercial R&D.
2. **PolitiFact-derived sets:** exclude (recommended), or request a Poynter license.
3. **ClaimReview storage policy:** use the API for discovery only; persist Data Commons items and our own paraphrased records.
4. **Post-cutoff threshold:** `review_date ≥ 2026-07-01`, plus the per-model cutoff table in `config/models.yaml`.
5. **Lossy mappings:** headline on exact and confirmed items, lossy reported separately (recommended)?
6. **"no evidence" ratings:** manual review (recommended), or auto-map to NEE?
7. **Annotation:** about 36 hours for 300 post-cutoff items. Who annotates? May a non-panel model pre-draft?
8. **Private individuals:** exclude `named_person` items about private individuals from all public views (recommended)?
9. **Debates:** confirm they're excluded from gold scoring.
10. **Smoke test:** approve the day-1 volume count (needs a Google API key) before committing to holdout ≥ 500.
11. **Open items:** the Data Commons CC BY version and its commercial wording; Fact-Check Insights terms; the Climate-FEVER and MultiFC licenses.
12. **Redistribution:** whether dev transcripts (which contain claim text) may be committed and published on the dashboard. That depends on the licenses above. Until then `runs/` stays gitignored.

*Sources consulted:* fever.ai · github.com/MichSchli/AVeriTeC · arxiv.org/abs/2305.13117 · arxiv.org/abs/2410.23850 · github.com/chengxuphd/liar2 · github.com/Tariq60/LIAR-PLUS · politifact.com/copyright · developers.google.com/fact-check/tools/api · developers.google.com/terms · datacommons.org/factcheck/download · datacommons.org/factcheck/faq · reporterslab.org/?p=3537 · poynter.org (ClaimReview snippets removal, 2025) · convokit.cornell.edu · webis.de/data/args-me-corpus.html · kialo.com/terms · github.com/allenai/scifact · arxiv.org/abs/2505.09414 · github.com/factiverse/QuanTemp · github.com/tdiggelm/climate-fever-dataset · huggingface.co dataset cards (health_fact, x-fact, multi_fc, ClaimReview2024plus) · arxiv.org/abs/2510.23508
