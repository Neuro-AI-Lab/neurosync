# AUDIT-C Korean-population research — validation studies, soju-unit item text, candidate admin-note

> **Mission:** `PLAN-2026-W29-B` step 1a (per `discussion.md`), T1 of the user directive "더 신뢰가능한
> 방향으로 진행" (trustworthy-direction resolution of the three open F3 decisions).
> **Author:** brainstorm | **Date:** 2026-07-13 | **Fabrication discipline:** hard rule — every
> factual claim carries a fetched source; every included item-text row is either
> `verbatim-from-source` with a fetchable citation + retrieval date, or reported as an explicit gap.
> No paraphrase, no back-translation, no reconstruction from memory anywhere in §3. Section 4 is the
> ONLY composed text in this file and is labeled as such throughout.
> **Decision authority:** this file enumerates candidates with evidence. It does **not** pick a
> Korean AUDIT-C cutoff — that adjudication belongs to `clinical-validator` (CVR-018) and the
> orchestrator (ADR-034), per `ADR-033`(2)'s standing deferral and this dispatch's brief.
> **Context read first:** `discussion.md` CVR-016 (Findings 5, 8), CVR-017 (Q3, Finding 4, register
> item 3), REV-038 §3, ADR-033 decisions 2–3; `docs/ai/item_bank_v1_sources.md` §5 + appendix
> §A5/§A6 (current v1 AUDIT-C: SBIRT Oregon Korean text, Western drink-units, international cutoffs
> male/unknown≥4, female≥3); VP-012 persona doc convention "소주 1병(≈7 standard drinks) 기준" (REV-038
> §3 quote).

---

## How to read this file

- **Verbatim-confidence** column contains only the literal string `verbatim-from-source` — nothing
  else is permitted in an included item-text row. If item text could not be verified verbatim, it is
  reported as a gap, never paraphrased or reconstructed.
- **Evidence tier** for validation-study claims: `[full PDF read]` (I fetched and read the complete
  article), `[direct fetch, structured extraction]` (I fetched the actual article page/PMC render and
  extracted structured content, not merely a search snippet), `[≥2 independent DB pages]` (abstract
  text confirmed identical across ≥2 independently-fetched bibliographic database pages — a stronger
  tier than a single search summary, per this project's established practice, but short of a full-text
  read), `[summary basis]` (a fetch-tool's own summary of a page I did not independently re-render, or
  a WebSearch synthesis only — flagged explicitly per this project's rule that summary-basis claims
  must say so).
- **Quoting discipline:** narrative claims (abstracts, discussion sections) are quoted in short
  fragments (≤20 words) per this project's citation discipline. Section 3's item/anchor text is
  quoted in FULL, verbatim, per the brief's explicit instruction that item-bank sourcing requires
  complete item reproduction (the same standard `item_bank_v1_sources.md` already applies).

---

## 1. Korean AUDIT-C / AUDIT-K validation-study table

Nine Korean-population studies located and read/fetched this session (two — Seong 2009 and Woo
2017 — were the brief's known leads; seven are newly found). All nine are Korean-authored,
Korean-population studies of the AUDIT family; six report an AUDIT-C-specific cutoff, three report
full-AUDIT/AUDIT-K cutoffs or AUROC only (included for population-match and cross-referencing
value, clearly marked).

| # | Study | N (sex) | Population | Reference standard | AUDIT-C cutoff (M/F/other) | AUROC (M/F) | Evidence tier |
|:--|:--|:--|:--|:--|:--|:--|:--|
| 1 | Kim JS et al. 1999 | 96 (96M) | Hospital patients, drinking history + alcohol-dependent inpatients | AUDIT-K itself (no external criterion) | N/A — full AUDIT-K only: 12/15/26 (problem/AUD/dependence) | not reported | full PDF read |
| 2 | Lee BW et al. 2000 | 86 (sex not reported in abstract) | Case-control: AUD patients (43) vs. non-AUD controls (43) | Clinical diagnosis | AUDIT-C-K: **8** (unified, not sex-split) | sens 0.95/spec 0.77 at cutoff 8 | summary basis |
| 3 | Seong JH et al. 2009 | 302 (302M) | University-hospital patients with drinking history | AUDIT-K total score (≥12 = "problem drinking") | **8** (male only; no female arm) | sens 82%/spec 76% | full PDF read |
| 4 | Kwon US et al. 2013 | 387 (198M/189F) | College students, student health center | DSM-IV-TR diagnostic interview | At-risk: **6(M)/4(F)**; AUD: **7(M)/6(F)** | 0.927(M)/0.921(F) at-risk; 0.902(M)/0.939(F) AUD | full PDF read (kjfm.or.kr) |
| 5 | Kim CG et al. 2014 | 435 (210M/225F) | Health-promotion-center comprehensive exam visitors | DSM-IV-TR diagnostic interview | N/A — full AUDIT-KR only: at-risk 3(M)/3(F); AUD 10(M)/8(F) | 0.946(M)/0.898(F) at-risk (AUDIT-KR) | direct fetch, structured extraction |
| 6 | Seo YR et al. 2016 | 400 (400F) | Health-promotion-center female drinkers | DSM-5 diagnostic interview | N/A — no cutoff reported; AUDIT-C AUROC only | 0.887 (F only) | direct fetch, structured extraction |
| 7 | Woo SM et al. 2017 | 509 (265M/244F) | Online community panel survey | NIAAA hazardous-drinking definition | **7(M)/6(F)** | not reported (cutoff-table only, no AUROC given in fetched abstract) | ≥2 independent DB pages |
| 8 | Lee KW et al. 2018 | 640 (375M/265F, 38 elderly) | Emergency department, injured patients | Whole-AUDIT score (≥8, WHO convention) | **5(M)/4(F)/4(elderly)** | 0.956(M)/0.966(F)/0.972(elderly) | full PDF read |
| 9 | Lee JH et al. 2018 | 46,450 (19,703M/26,747F) | KNHANES waves 4–6, nationally representative | Whole-AUDIT score (WHO cutoffs 8M/7F/7elderly) | Unified **5**; sex-split **6(M)/5(F)**; elderly **3** | 0.981 overall; 93.0%sens/87.5%spec(M), 90.3%/93.6%(F) | direct fetch, structured extraction |

**International reference point (for scale):** Bush et al. 1998 (US, the source of this project's
current v1 implementation) — male/unknown ≥4, female ≥3. All nine Korean studies above except #2
and #8's female/elderly arms report a Korean-derived cutoff at or above this convention; six of the
seven AUDIT-C-specific numbers (#2, #3, #4-AUD, #7, #9-unified/male) exceed it, one arm is exactly
at it (#9-female=5 vs. int'l 4, #8's own values sit closer: 5M/4F), and #8 (ED) is the one study
whose numbers sit closest to the international convention (5M/4F, essentially +1 over Bush et al.).
**Direction is not uniform across all nine — #8 is a genuine outlier toward the international
number, reported honestly, not smoothed into the majority pattern.**

### Per-study detail with sourced quotes

**[1] Kim JS, Oh MK, Park BK, Lee MK, Kim GJ, Oh JK (1999).** "한국에서 Alcohol use disorders
identification test(AUDIT)를 통한 알코올리즘의 선별 기준." *J Korean Acad Fam Med* 20(9):1152-1159.
Already sourced in `item_bank_v1_sources.md` §A7 (full PDF read this project). Quote: *"The authors
recommend AUDIT cut-off scores of 12 points as the standard value for a broader sense of 'problem
drinking'... 15 for 'alcohol use disorders'... and 26 for 'alcohol dependence.'"* Method: "85 drinking
men and 11 male alcohol dependents." This is the full 10-item AUDIT-K, not AUDIT-C-specific — no item
appendix in the accessible pages. Retrieved 2026-07-13 (carried from prior dispatch).

**[2] Lee BW, Lee CH, Lee PG, Choi MJ, Namkung K (2000).** "한국어판 알코올 사용장애 진단 검사(AUDIT :
Alcohol Use Disorders Identification Test)의 개발 : 신뢰도 및 타당도 검사." *J Korean Acad Addict
Psychiatry* 4(2):85-94. Fetched via YUHSpace (Yonsei University institutional repository) 2026-07-13:
`https://ir.ymlib.yonsei.ac.kr/handle/22282913/172500`. **[summary basis — repository landing-page
summary, not a re-rendered full PDF]**. This appears to be an independent, earlier development
lineage from Kim JS et al. 1999 (different authors, different journal, case-control N=86 design
rather than a drinking-history clinical sample). Reported findings: "AUDIT-K optimal cutoff: 12
(sensitivity=0.84, specificity=0.86)"; **"AUDIT-C-K optimal cutoff: 8 (sensitivity=0.95,
specificity=0.77)."** Sex composition of the 86 participants is not given in the accessible summary —
flagged as a population-match gap. Author romanization is best-effort from the repository's own
Korean-script listing (이병욱/이충헌/이필구/최문종/남궁기); the journal's own English-language
Romanized author string was not independently confirmed this session — flagged `UNVERIFIED` for
exact spelling only, not for the substantive findings, which come from the repository's own
structured record.

**[3] Seong JH, Lee CH, Do HJ, Oh SW, Lym YL, Choi JK, Joh HK, Kweon KJ, Cho DY (2009).**
"일차진료에서 문제음주자 선별을 위한 AUDIT-C의 타당도 조사." *Korean J Fam Med* 30(9):695-702.
doi:10.4082/kjfm.2009.30.9.695. Already sourced in `item_bank_v1_sources.md` §A6 (full PDF read).
Quote: *"we designated the score 8 or more as problem drinking"* (sens 82%/spec 76%). N=302, male
only. Paper explicitly discusses why the Korean-derived number is higher than international
convention, attributing it partly to AUDIT-K's own higher screening threshold as the criterion, not
necessarily a true per-drink-harm difference. Retrieved 2026-07-13 (carried from prior dispatch).

**[4] Kwon US, Kim JS, Kim SS, Jung JG, Yoon SJ, Kim SG (2013).** "Utility of the Alcohol
Consumption Questions in the Alcohol Use Disorders Identification Test for Screening At-Risk
Drinking and Alcohol Use Disorders among Korean College Students." *Korean J Fam Med* 34(4):272-280.
doi:10.4082/kjfm.2013.34.4.272. Fetched directly 2026-07-13:
`https://www.kjfm.or.kr/journal/view.php?doi=10.4082/kjfm.2013.34.4.272` (open-access, CC-BY-NC).
**[full text read — kjfm.or.kr's own rendered article page, structured tables extracted directly, not
a search summary]**. N=387 (198M/189F), Chungnam National University student health center,
March-May 2011. Reference standard: DSM-IV-TR structured diagnostic interview. At-risk-drinking
AUDIT-C cutoff **≥6 males (sens 81.3%/spec 88.8%, AUROC 0.927), ≥4 females (sens 77.2%/spec 93.6%,
AUROC 0.921)**. AUD AUDIT-C cutoff **≥7 males (sens 85.7%/spec 85.9%, AUROC 0.902), ≥6 females (sens
83.3%/spec 91.2%, AUROC 0.939)**. This is the only study in this table with BOTH sexes AND two
distinct clinical outcomes (at-risk vs. AUD) reported separately for AUDIT-C specifically.

**[5] Kim CG, Kim JS, Jung JG, Kim SS, Yoon SJ, Suh HS (2014).** "Reliability and Validity of
Alcohol Use Disorder Identification Test-Korean Revised Version for Screening At-risk Drinking and
Alcohol Use Disorders." *Korean J Fam Med* 35(1):2-10. doi:10.4082/kjfm.2014.35.1.2. PMID 24501664.
Fetched 2026-07-13: `https://pmc.ncbi.nlm.nih.gov/articles/PMC3912263/`. **[direct fetch, structured
extraction from the PMC-rendered article]**. N=435 (210M/225F, under 65), Chungnam National
University Hospital Health Promotion Center comprehensive-exam visitors, Jan-Jun 2012. Reference
standard: DSM-IV-TR structured interview. **This paper reports full AUDIT-KR (10-item) cutoffs only —
no AUDIT-C-specific number.** At-risk AUDIT-KR: 3(M, sens 93.69/spec 78.79, AUROC 0.946)/3(F, sens
92.40/spec 78.08, AUROC 0.898). AUD AUDIT-KR: 10(M, sens 100.00/spec 89.51, AUROC 0.982)/8(F, sens
100.00/spec 93.71, AUROC 0.983). Cronbach's α = 0.885. Included for population-match value (best
health-checkup-population match with sex-stratified DSM-anchored data) and as corroborating context
for the AUD-severity end of the Korean AUDIT-K literature.

**[6] Seo YR, Kim JS, Kim SS, Yoon SJ, Suh WY, Youn K (2016).** "Development of a Simple Tool for
Identifying Alcohol Use Disorder in Female Korean Drinkers from Previous Questionnaires." *Korean J
Fam Med*. Fetched 2026-07-13: `https://pmc.ncbi.nlm.nih.gov/articles/PMC4754281/`. **[direct fetch,
structured extraction]**. N=400 women only, Chungnam National University Hospital health promotion
center, June 2013-May 2014, drinkers in the past month. Reference standard: DSM-5 structured
interview. **No AUDIT-C-specific cutoff for women is reported** — the paper's contribution is a novel
2-item tool (AUDIT items 5+7), reported as AUROC 0.958 vs. AUDIT-C's own AUROC of **0.887** in the
same female sample (no cutoff value given alongside that AUROC in the fetched extraction). Included
because it is the only Korean study located this session that is a dedicated, single-sex (female)
AUDIT validation sample of appreciable size (N=400) — directly relevant to the brief's "does the
study validate a female cutoff at all" question, answered here as: AUROC yes, cutoff no.

**[7] Woo SM, Jang OJ, Choi HK, Lee YR (2017).** "위험음주자 선별을 위한 한국판 알코올사용장애
선별검사(AUDIT-K), 알코올 소비 점수(AUDIT-C), 3번 문항(AUDIT3)의 유용성과 최적 절단값." *J Korean
Acad Addict Psychiatry* 21(2):62-67. doi:10.37122/kaap.2017.21.2.62. Retrieved 2026-07-13 directly
from **two independent bibliographic-database pages**, both displaying the identical English
abstract: DBpia (`https://www.dbpia.co.kr/journal/articleDetail?nodeId=NODE10816175`) and 학지사
Kyobobook Scholar (`https://scholar.kyobobook.co.kr/article/detail/4010026311468`). **[≥2 independent
DB pages, upgraded from the prior dispatch's summary-basis-only tier]**. Quote (verbatim, identical
on both pages): *"Suggestible cut off scores of AUDIT-C and AUDIT3 for hazardous drinking were 7 and
3 for males and 6 and 3 for females."* Also: AUDIT-K itself, 11(M)/7(F). N=509 (265M/244F), online
panel survey Feb 10-15 2016, NIAAA hazardous-drinking criterion (external, not AUDIT-derived —
avoids the criterion-circularity risk several other studies in this table carry).

**[8] Lee KW, Choi YH, Lee JH (2018).** "Cut-off points for screening at-risk drinking by AUDIT-C
Korean version at emergency department." *Turkish J Emerg Med* 18(2):57-61.
doi:10.1016/j.tjem.2018.03.001. PMID 29922731. Fetched 2026-07-13, full open-access PDF:
`https://auditscreen.org/cmsb/uploads/2018-cut-off-points-for-screening-at-risk-drinking-by-audit-c-korean-version-at-emergency-department.pdf`.
**[full PDF read, all 5 pages]**. N=640 (375M/58.4%, 265F/41.4%, 38 elderly ≥65), injured patients
presenting to the ED of Ewha Womans University Mokdong Hospital, May-Sep 2010 (KCDC-supervised
project). Reference standard: whole-AUDIT score ≥8 (WHO convention), also re-analyzed at ≥7 for
women/elderly per WHO's own sensitivity note — cutoff answer did not change. Quote (verbatim):
*"Cut-off points were 5 for men [AUROC 0.956], 4 for women (AUROC 0.966), and 4 in elders."* Explicit
full item table for AUDIT-C is reproduced in the paper in English (not Korean — the paper's Table 1
is in English despite the study population being Korean; no Korean item text appendix). This is the
**first Korean study to report AUDIT-C cutoffs for women AND an elderly subgroup together**, and the
one outlier toward the international 4/3 convention rather than the higher-cutoff majority pattern.

**[9] Lee JH, Kong KA, Lee DH, Choi YH, Jung KY (2018).** "Validation and proposal for cut-off
values of an abbreviated version of the Alcohol Use Disorder Identification Test using the Korean
National Health and Nutrition Examination Survey." *Clin Exp Emerg Med* 5(2):113-119.
doi:10.15441/ceem.17.228. PMID 29973036. Fetched 2026-07-13:
`https://pmc.ncbi.nlm.nih.gov/articles/PMC6039362/`. **[direct fetch, structured extraction from the
PMC-rendered article, plus a targeted verbatim-quote re-fetch]**. N=46,450 adults ≥19 (19,703M/42.4%,
26,747F/57.6%) from **KNHANES waves 4-6 (2007-2015)**, Korea's nationally representative health and
nutrition survey — by far the largest and most population-representative sample in this table.
Reference standard: whole-AUDIT score against WHO cutoffs (8M/7F/7 elderly) — note this carries the
same AUDIT-C-is-a-subset-of-AUDIT circularity concern flagged for studies #1, #3, and #8. Quote
(verbatim): *"The most appropriate cut-off values for the AUDIT-Q3 alone, AUDIT-QF, AUDIT-C,
AUDIT-4, and AUDIT-PC for all adults over 19 years were 2, 4, 5, 6, and 4 points, respectively."*
Sex-specific breakdown (structured extraction, not itself directly quoted verbatim from the PMC
render): AUDIT-C 6(M)/5(F)/3(elderly). AUROC 0.981 overall; sens/spec 93.0%/87.5%(M), 90.3%/93.6%(F).
Note this author group substantially overlaps with study #8's authors (Jae Hee Lee, Yoon Hee Choi
common to both) — related research group, but genuinely distinct populations (ED trauma patients
vs. nationally representative survey respondents) and distinct outcomes (5M/4F vs. 6M/5F) — **not
the same finding reported twice**, flagged here explicitly so the two are not conflated downstream.

---

## 2. Population-match analysis

**This project's use case:** non-diagnostic pre-consultation mental-health intake screening of
general adult Koreans presenting for a routine visit — not a treatment-seeking alcohol clinic
population, not an ED/trauma-triage population, not a college-only population. The closest
structural analogue among the nine studies is a general-population or routine-health-checkup
sample with broad age/sex coverage and a criterion that does not itself derive from the AUDIT-C
items being validated (criterion independence).

| # | Study | Sample size weight | Sex coverage | Population-type match | Criterion independence | Citation weight |
|:--|:--|:--|:--|:--|:--|:--|
| 9 | Lee JH et al. 2018 (KNHANES) | Very high (N=46,450, largest by 2 orders of magnitude) | Both, near-parity | **Best** — nationally representative general population, no clinical/treatment selection | Weak — whole-AUDIT-score criterion (same-instrument subset) | Peer-reviewed, indexed journal (Clin Exp Emerg Med) |
| 5 | Kim CG et al. 2014 | Moderate (N=435) | Both, near-parity | **Strong** — comprehensive-exam-center visitors, not alcohol-treatment-seeking, but no AUDIT-C-specific cutoff (full AUDIT-KR only) | Strong — independent DSM-IV-TR interview | Peer-reviewed (Korean J Fam Med) |
| 6 | Seo YR et al. 2016 | Moderate (N=400, F only) | Female only | **Strong** — same health-checkup-center population type as #5, but no cutoff, AUROC only | Strong — independent DSM-5 interview | Peer-reviewed (Korean J Fam Med) |
| 8 | Lee KW et al. 2018 (ED) | High (N=640) | Both + elderly subgroup | **Moderate** — general-population intercept (injured patients, not alcohol-selected) but ED/trauma setting differs meaningfully in acuity/context from a calm pre-consultation intake | Weak — whole-AUDIT-score criterion | Peer-reviewed (Turkish J Emerg Med) |
| 7 | Woo SM et al. 2017 | Moderate (N=509) | Both, near-parity | **Moderate-strong** — online community panel, self-selected but not treatment-seeking, closest to "general adult respondent" outside KNHANES | Strong — independent NIAAA criterion | Peer-reviewed (J Korean Acad Addict Psychiatry) |
| 4 | Kwon US et al. 2013 | Moderate (N=387) | Both, near-parity | **Moderate** — general (non-treatment-seeking) population but age-restricted to college students, not representative of the full adult age range this project's patients span | Strong — independent DSM-IV-TR interview | Peer-reviewed (Korean J Fam Med) |
| 3 | Seong JH et al. 2009 | Moderate (N=302) | **Male only, no female arm** | **Weak** — university-hospital patients "with drinking history" is a selection criterion adjacent to treatment-context, and the known lead this dispatch was asked to verify | Weak — AUDIT-K-total criterion (same-instrument) | Peer-reviewed (Korean J Fam Med) |
| 2 | Lee BW et al. 2000 | Low (N=86) | **Not reported** — cannot confirm sex coverage | **Weak** — explicit case-control design (43 AUD patients vs. 43 non-AUD controls); extreme-groups designs are known to inflate accuracy metrics relative to a continuous general population | Moderate — clinical diagnosis, but case-control | Institutional repository record, not independently confirmed via the journal itself |
| 1 | Kim JS et al. 1999 | Low (N=96) | **Male only**, and skewed toward alcohol-dependent inpatients | **Weakest** — explicitly a clinical/dependent population; also not AUDIT-C-specific | N/A (full-scale AUDIT-K only, no external criterion beyond the instrument's own bands) | Peer-reviewed (J Korean Acad Fam Med), but oldest and narrowest sample |

**Observations for clinical-validator's adjudication (not a recommendation):**

- **Female cutoff coverage** exists for AUDIT-C specifically in three studies (#4 Kwon 2013, #7 Woo
  2017, #8 Lee 2018-ED) and #9's KNHANES sex-split — four independent female-specific AUDIT-C
  numbers: 4 (at-risk, college), 6 (women, community), 4 (ED), 5 (KNHANES). These four numbers alone
  span the full 4-6 range, i.e. even restricting to "AUDIT-C cutoff for Korean women" there is no
  single consensus value across population types. #3 Seong 2009 and #1 Kim 1999 have **no female
  arm at all** — if either of those is weighted heavily for the male cutoff, the project would still
  need a separate source for the female cutoff, since neither validates one.
- **Criterion circularity** is a real methodological concern for #1, #3, #8, and #9 — all four
  validate AUDIT-C against a score derived from the same 10-item AUDIT instrument (AUDIT-C is items
  1-3 of that instrument), which mechanically inflates AUROC/sensitivity relative to validation
  against an independent criterion. #4, #5, #6, #7 use an external criterion (DSM interview or NIAAA
  definition) and are less exposed to this concern — worth weighting accordingly.
- **The largest, most population-representative study (#9, KNHANES, N=46,450) gives cutoffs
  (6M/5F) that sit almost exactly midway between the international convention (4M/3F) and the
  highest Korean numbers found (8, #2/#3)** — it is not the outlier in either direction.
- **The one study closest in raw population type to "general adult presenting for routine care"
  outside KNHANES (#5, health-checkup center) does not give an AUDIT-C-specific number** — only
  full-AUDIT-KR bands (3 at-risk / 10 AUD for men). If clinical-validator wants the tightest
  population match with an independent criterion, #5's full-AUDIT-KR at-risk cutoff (3M/3F) is
  available as an indirect anchor, but is not directly comparable to a 3-item AUDIT-C score.
- **No single study in this table is a perfect match** to "non-diagnostic pre-consultation
  mental-health intake, general adult, not alcohol-treatment-seeking" — #9 (KNHANES) is closest on
  population representativeness but weakest on criterion independence; #4/#6/#7 are closest on
  criterion independence but narrower on population (#4 college-age only, #6 female-only-no-cutoff,
  #7 online-panel self-selection). This tradeoff, not a single winning number, is what this section
  reports for adjudication.
- **Contamination/pretraining-overlap note (not the standard ML-benchmark sense, but relevant
  here):** this project's F3 module uses an LLM (K-EXAONE) to simulate a patient answering AUDIT-C
  items in Korean. If that model has seen official Korean AUDIT/AUDIT-K text (all nine studies here
  are published, indexed, publicly accessible papers, several open-access) during pretraining, that
  is arguably a *feature* for simulation fidelity (the model would recognize the real instrument),
  not a leakage risk in the usual train/test-split sense — there is no benchmark/held-out-answer set
  here whose "test" integrity this could compromise. No contamination action item follows from this.

---

## 3. Verbatim Korean item-text re-sourcing (soju-unit framing)

**Result: FOUND.** Korea's official national/workplace health-screening system has a dedicated
10-item alcohol-lifestyle assessment form — **[별지 제15호의3서식] 음주 생활습관 평가 도구**
("Drinking Lifestyle Assessment Tool") — issued under the same 보건복지부고시 "건강검진 실시기준"
(Ministry of Health and Welfare notice, "Health Examination Implementation Standards") regulatory
instrument that already supplies this project's government-form PHQ-9 alternate (별지 제14호서식,
already sourced in `item_bank_v1_sources.md` §1.1/§A3). Items 1-3 of this form are the Korean
AUDIT-C-equivalent subset, and item 2 offers an explicit **소주(soju)-bottle-based response track**,
and item 3's binge-drinking question is explicitly calibrated in **소주 1병 / 맥주 5캔** terms rather
than a Western "6-or-more standard drinks" framing. This is the officially-issued Korean form the
brief asked me to look for, not a composed or back-translated substitute.

### 3.1 Provenance and cross-verification

Retrieved from **two independent mirrors**, both 2026-07-13:

1. `https://www.elandclinic.com/Download/Documents/음주생활습관평가도구(검진자용).pdf` — a clean
   standalone PDF titled "음주 생활습관 평가 도구" (10 items) + a companion "금주/절주 처방전"
   (abstinence/moderation prescription) page that explicitly labels the total score field
   **"음주생활습관 평가 점수(AUDIT-KR)"** — i.e. this instrument's own regulatory documentation names
   it AUDIT-KR. **[full PDF read, both pages]**
2. `https://epower.hanilmed.net/upload/2021_생활습관포함서식.pdf` — a compiled, multi-form packet
   (workplace/occupational health-screening context) that includes, in sequence: [별지 제13호의3서식]
   생활습관평가 결과기록지 (summary record), **[별지 제14호서식] 정신건강검사(우울증) 평가도구
   (PHQ-9)** — byte-identical to this project's already-sourced government-form PHQ-9
   (`item_bank_v1_sources.md` §A3) — [별지 제15호의 7서식] 영양 (nutrition), [별지 제15호서식] 흡연
   (smoking), **[별지 제15호의 3서식] 음주 생활습관 평가 도구 (alcohol)**, [별지 제15호의 5서식] 운동
   (exercise), [별지 제15호의 9서식] 비만 (obesity), and [별지 제13호서식] 인지기능장애 (cognitive
   screening). **[full PDF read, all 10 pages]**

**This second mirror is the load-bearing find**: it establishes the exact official form number
(별지 제15호의3서식) AND, by containing the PHQ-9 form this project already independently verified
as government-sourced, cross-confirms that both instruments come from the same regulatory document
family — strong provenance corroboration, not a standalone or unofficial site.

**One discrepancy found between the two mirrors, disclosed not resolved:** mirror 1 (elandclinic)
gives item 1 five response anchors including "전혀 안 마신다(0점)"; mirror 2 (hanilmed/epower) gives
only four anchors for item 1, apparently missing the "전혀 안 마신다(0점)" option (item 1 in mirror 2
begins directly at "한 달에 1번 이하(1점)"). All other items (2-10) are byte-identical between the two
mirrors on independent reading. This could be a scan/OCR dropout in mirror 2 (a checkbox glyph lost
in the compiled-packet's page rendering) rather than a genuine form difference — the "0점" anchor is
standard AUDIT item-1 structure and is present in every other Korean/international AUDIT-family
source this project has fetched. Reported honestly as an unresolved minor discrepancy, not silently
picked one way.

### 3.2 Item table — AUDIT-C-equivalent items (1-3 of the 10-item official form)

| # | Korean item text (원문, verbatim) | Response anchors (verbatim) | Verbatim-confidence | Source |
|:--|:--|:--|:--|:--|
| 1 | 술을 마시는 횟수는 어느 정도입니까? | 전혀 안 마신다(0점) / 한 달에 1번 이하(1점) / 한 달에 2~4번(2점) / 일주일에 2~3번(3점) / 일주일에 4번 이상(4점) | verbatim-from-source | 별지 제15호의3서식, mirror 1 (elandclinic.com), retrieved 2026-07-13 — see §3.1 discrepancy note on mirror 2's apparent 0-anchor dropout |
| 2 | 술을 마시는 날은 보통 어느 정도 마십니까? (아래의 두 곳 중 주로 드시는 술을 선택하여 한 곳에 표시해 주시면 됩니다.) | **소주 트랙**: 반병 이하(0점) / 1병 이하(1점) / 1.5병정도(2점) / 2병정도(3점) / 2.5병 이상(4점). **기타 술 트랙** (양주·와인은 각각의 술잔; 막걸리는 한 사발=1잔; 맥주는 캔맥주 1캔 또는 작은 병맥주 1병=1잔, 생맥주 500cc=1.3잔): 1~2잔(0점) / 3~4잔(1점) / 5~6잔(2점) / 7~9잔(3점) / 10잔 이상(4점) | verbatim-from-source | 별지 제15호의3서식, both mirrors, byte-identical, retrieved 2026-07-13 |
| 3 | 한 번의 술좌석에서 소주 1병을 초과하거나 맥주 5캔(생맥주 2,000cc) 이상*을 마시는 횟수는 어느 정도입니까? (*알코올 60g에 해당하는 음주량을 의미한다. / 양주, 와인, 막걸리는 각각의 술잔으로 5잔 이상) | 전혀 없다(0점) / 한 달에 한 번 미만(1점) / 한 달에 한 번 정도(2점) / 일주일에 한 번 정도(3점) / 거의 매일(4점) | verbatim-from-source | 별지 제15호의3서식, both mirrors, byte-identical, retrieved 2026-07-13 |

**Structural note (important for developer/clinical-validator, not a translation nuance):** this
official Korean form's AUDIT-C-equivalent structure genuinely differs from the current v1
implementation's SBIRT-Oregon-sourced AUDIT-C (`item_bank_v1_sources.md` §5.2/§5.3), not merely in
unit labels:

- **Item 2 is bifurcated** into a soju-bottle track and a glasses-of-other-drinks track, with an
  explicit conversion table for beer/makgeolli/draft beer — the current v1 item 2 has a single,
  Western-unit-only anchor set (355mL beer/148mL wine/44mL spirits = "1 잔").
- **Item 3's binge question is calibrated by an explicit alcohol-mass threshold (60g), expressed in
  소주-bottle/맥주-can terms**, not by a "6 or more drinks in one occasion" count the way the current
  v1 item 3 (and the international WHO AUDIT) frames it.
- Full 10-item form uses the standard 0-4/0-4/.../0-2-4 WHO-AUDIT point structure (items 1-8 each
  0-4, items 9-10 each 0/2/4) — consistent with genuine AUDIT-K, not an ad-hoc local variant.

### 3.3 Cross-reference to prior sourcing

Seong et al. 2009 (already fully read for this project, `item_bank_v1_sources.md` §A6) independently
describes AUDIT-K's binge item as calibrated to *"소주 1병 또는 맥주 4병 이상"* — structurally the
same soju/beer-can framing family as the item 3 found here (though not byte-identical wording: "맥주
4병" there vs. "맥주 5캔(생맥주 2,000cc)" here — plausibly different form revisions or Seong's own
paraphrase of the item rather than a literal quote, since Seong's paper does not itself carry an item
appendix). This is corroborating, not contradicting, evidence that a soju-calibrated Korean AUDIT-C
binge item genuinely exists in the Korean screening ecosystem — the form found this session is the
first byte-level verbatim source for it located by this project.

### 3.4 Gaps

Items 4-10 of the 10-item form (dependence/harm items, outside AUDIT-C's 3-item scope) are also
verbatim-sourced from the same two mirrors but are out of scope for this dispatch (AUDIT-C is items
1-3 only) — available if a future full-AUDIT-K sourcing pass is requested. The exact `law.go.kr`
canonical PDF of 별지 제15호의3서식 was not independently reached this session (see §5 retry log) —
the two mirrors used are not the primary regulatory host, though one (hanilmed/epower) is packaged
alongside this project's already-verified official PHQ-9 text, which is strong but not definitive
corroboration of canonical-source identity. Byte-identity to the specific item wording used by any
of the nine validation studies in §1 is **not confirmed** — none of those papers reproduce a Korean
item-text appendix (same limitation already disclosed for the SBIRT-Oregon text in
`item_bank_v1_sources.md` §5.1).

---

## 4. Candidate administration-note text — composed, NOT item text, clinical-validator-gated

> **NON-VALIDATED COMPOSED METADATA — NOT ITEM TEXT.** Everything below this line in §4 is
> brainstorm-authored explanatory text, not a sourced instrument quote. It must not be administered
> as if it were a scored item, and must not ship without `clinical-validator` review/gate. Flagged
> per the brief's explicit requirement that this is the only composed text this file may contain.

**Purpose:** a short metadata note explaining the relationship between this project's current
Western-standard-drink AUDIT-C item text (`item_bank_v1_sources.md` §5, "1 잔의 기준: 12
온스(355mL) 맥주 / 5 온스(148mL) 와인 / 1.5 온스(44mL) 독주") and the soju-unit convention already
used elsewhere in this project's own persona documentation (VP-012: "소주 1병(≈7 standard drinks)
기준 7-9잔 구간", per REV-038 §3) — so a patient answering in soju terms is not structurally
mismatched against Western-unit anchors (the confound REV-038/CVR-017 already found live in EXP-020
Cell C).

**Candidate Korean text (draft, composed, unsourced — clinical-validator to edit/reject freely):**

> ※ 참고 (비검증 구성 문구 — 실제 척도 문항 아님): 위 음주량 기준(맥주 12온스/와인 5온스/증류주
> 1.5온스 = 1잔)은 서구식 표준잔 정의를 따릅니다. 소주로 답변하실 경우, 소주 1병(약 360mL, 알코올
> 도수 16-17% 기준)은 대략 7표준잔 정도에 해당하는 것으로 참고하실 수 있습니다. 이 환산은 근사치이며
> 공식 척도 문항이 아닙니다.

**English gloss of the composed note (for reviewers, not for administration):** "Note (unvalidated
composed text — not an actual scale item): the standard-drink definitions above (12oz beer/5oz
wine/1.5oz spirits = 1 drink) follow the Western convention. If answering in soju terms, one bottle
of soju (~360mL, ~16-17% ABV) can be referenced as roughly 7 standard drinks. This conversion is
approximate and is not an official scale item."

**Known weaknesses of this draft, flagged for clinical-validator, not resolved here:**

- The "≈7 standard drinks per soju bottle" figure is carried forward from the project's own VP-012
  persona-document convention (REV-038 §3), not independently re-derived or sourced in this
  dispatch — it is presented here as an internal-consistency choice (matching what the project
  already uses elsewhere), not as a clinically validated conversion factor. A soju bottle's actual
  standard-drink count depends on the ABV assumption and the standard-drink-gram definition used
  (WHO ≈10g pure alcohol vs. Korean MOHW's own 7g convention, both already noted with citations in
  `item_bank_v1_sources.md` §5.3) — this note does not resolve which convention is correct, only
  restates the figure already in use.
  - Recommended alternative if clinical-validator prefers the *officially sourced* Korean anchor
    system over a composed conversion note: **replace item 2's western-unit anchor set with §3.2's
    verbatim 소주-track anchors (반병 이하/1병 이하/1.5병정도/2병정도/2.5병 이상)** — this sidesteps
    the need for any composed conversion text entirely, since the sourced Korean form already asks
    the question natively in soju-bottle terms. That is a code/content decision for
    developer + clinical-validator, not something this brainstorm dispatch can implement.
- This note does not itself resolve the item-3 binge-question structural difference (§3.2's
  structural note) — a soju-calibrated conversion note attached only to item 2 would leave item 3's
  "6+ drinks" vs. "소주 1병 초과/맥주 5캔" framing gap unaddressed.
- Composed by brainstorm under time/scope constraints of a single dispatch — has not been reviewed
  for tone, register-appropriateness, or clinical adequacy by anyone. Treat as a strawman starting
  point only.

---

## 5. Retry / attempt log

| # | Source tried | Method | Outcome |
|:--|:--|:--|:--|
| 1 | `elandclinic.com` "음주생활습관평가도구(검진자용).pdf" | WebFetch → saved PDF → Read | **Fetched, full PDF read** — primary find, §3 |
| 2 | `iserim.co.kr` "건강검진 문진표.pdf" | WebFetch → saved PDF → Read | Fetched but contained no alcohol/AUDIT item content in the readable text (font/structure data only, appears to be a different/generic checkup form) — not used |
| 3 | `khepi.or.kr` (절주온, Korea Health Promotion Institute) board page for "알코올 사용장애 선별검사 도구" (2017), attachment "AUDIT-K 설문지 및 행동지침.pdf" | WebFetch on the board page (rendered, listed the attachment filename) | Board page rendered; the attachment PDF's own direct download URL was not exposed in the rendered page (JS-triggered download, same class of dead end as prior NCMH findings in project memory) — not fetched |
| 4 | `law.go.kr` `flDownload.do?flSeq=92059635` (건강검진 실시기준, full regulation text incl. forms) | WebFetch → saved binary → Read | Fetched but the file is HWP-encoded and rendered as garbled/undecodable text — consistent dead-end pattern for this host, already documented in prior sourcing note | 
| 5 | `epower.hanilmed.net` "2021_생활습관포함서식.pdf" | WebFetch → saved PDF → Read | **Fetched, full PDF read, all 10 pages** — second independent mirror, cross-confirms official 별지 제15호의3서식 numbering + PHQ-9 byte-identity, §3.1 |
| 6 | `synapse.koreamed.org/articles/1017850` (attempted alternate route to Woo et al. 2017 full text) | WebFetch | Connection refused (`ECONNREFUSED`) — not reachable this session |
| 7 | KCI page for Woo et al. 2017 | Not attempted this session (2 independent DB pages already obtained via DBpia + Kyobobook Scholar; diminishing marginal value against session budget) | Not tried — noted as a possible future 3rd-mirror confirmation if ever needed |
| 8 | `dsr5000.com` self-test AUDIT-K aggregator | Noted in prior sourcing note as located but non-authoritative (not a government/peer-reviewed source) | Not re-fetched this session; not used |
| 9 | PMC8431181 "Validation of the AUDIT and AUDIT-C for Hazardous Drinking in Community-Dwelling Older Adults" | WebFetch, checked for Korean population | **Excluded — Belgian (Flemish) population, not Korean.** Confirmed directly, not assumed from title. |
| 10 | PMC4862044 "AUDIT-C is more useful than pre-existing laboratory tests..." | WebFetch, checked for Korean population | **Excluded — Japanese population (Osaka), not Korean.** Confirmed directly. |
| 11 | KNHANES-direct search ("국민건강영양조사 AUDIT-C 한국 성인") | WebSearch | Led to study #9 (Lee JH et al. 2018, which itself uses KNHANES waves 4-6) — no separate/additional KNHANES-based AUDIT-C paper found beyond #9 |
| 12 | "Screening Test for At-Risk Drinking... STAD" (Lee, Jung, Choi, KNHANES-derived 2-item tool) | WebSearch only | Located (DOI 10.1155/2018/2306587) but not fetched/read this session — a DIFFERENT abbreviated instrument (2-question STAD, not AUDIT-C), out of this dispatch's scope (AUDIT-C specifically); noted here so a future session recognizes it rather than re-discovering it |
| 13 | KHEPI 절주온 "나의 음주 습관은.PNG" cardnews attachment | Found via board-page fetch (#3) | Not pursued — an image file, unlikely to contain independently useful item text beyond what §3 already has |
| 14 | BMC Psychology 2025 "Development and preliminary validation of mental health check-up questionnaire in Korea" (Choi & Lee 2025) | WebFetch (PMC12639728) | **Fetched, relevant context obtained** — not an AUDIT-C validation study itself, but directly precedent-setting: uses AUDIT-K as a validation instrument for a Korean non-diagnostic mental-health check-up questionnaire's alcohol-problems domain (N=500, general population panel, r=0.69 with AUDIT-K). Cited in §2 framing, not in the §1 cutoff table (it reports no independent AUDIT-C cutoff of its own). |

---

## 6. Summary table (for clinical-validator/orchestrator quick reference)

| Deliverable | Status |
|:--|:--|
| Korean AUDIT-C/AUDIT-K validation studies located | 9 (2 known leads verified + 7 newly found), spanning 1999-2018, all sourced with fetchable citations |
| Studies with an AUDIT-C-specific cutoff | 6 of 9 (#2, #3, #4, #7, #8, #9) |
| Studies with a female-specific AUDIT-C cutoff | 3 of 9 (#4: 4, #7: 6, #8: 4) + #9's sex-split (5) |
| Studies with zero female arm | 2 of 9 (#1, #3 — including the brief's own "Seong 2009" lead) |
| Best population-representativeness match | #9 (KNHANES, N=46,450) — but weakest on criterion independence |
| Best criterion-independence match | #4/#6/#7 (external DSM/NIAAA criteria) — but narrower populations |
| Verbatim Korean AUDIT-C item text with soju-unit framing | **Found** — 별지 제15호의3서식, 2 independent mirrors, §3.2 |
| Composed administration-note text | Drafted, explicitly flagged non-validated, §4 — clinical-validator gate required before any use |
| Cutoff decision | **Not made here** — routed to CVR-018/ADR-034 per this dispatch's scope boundary |

**Linked:** `PLAN-2026-W29-B`, CVR-016, CVR-017, REV-038, REV-039, ADR-033, `item_bank_v1_sources.md`
§5, VP-012 persona doc, EXP-020 Cell C.
