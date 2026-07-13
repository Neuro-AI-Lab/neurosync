# Item bank v1 — sourced Korean instrument reference (PHQ-9, GAD-7, PHQ-4, WHO-5, AUDIT-C)

> **Mission:** `PLAN-2026-W29-A` step 1 (per `discussion.md`), answering `STATE-2026-07-12d`'s open
> user question ("PHQ-9/GAD-7 등 공식 psychiatry standards를 research를 통해 reproduce하라").
> **Author:** brainstorm | **Date:** 2026-07-13 | **Fabrication discipline:** hard rule — every
> Korean item row below is either `verbatim-from-source` with a fetchable citation, or ABSENT and
> listed in that instrument's Gaps section. No paraphrase, no back-translation, no reconstruction
> from memory anywhere in this file.
> **Deliverable scope note:** this file is the sole deliverable of this dispatch per the brief
> (`docs/ai/f3_quick_dev_plan.md` §2.3's open question). No code, no `discussion.md`/root-doc
> writes — those are explicitly out of scope for this dispatch.
> **2026-07-13 addendum (second dispatch):** §4 (WHO-5) updated in place with a retry — no new
> Korean item text obtained, but the primary Korean-language citation was identified and the
> raw<13 cutoff evidence upgraded from summary-basis to directly-sourced/triply-confirmed. All
> other sections (§1-3, §5) are untouched from the first dispatch, per that dispatch's scope.
> **2026-07-13 addendum (third dispatch, appendix-completion pass — CVR-016 condition 4 / ADR-033
> decision 4):** re-fetched Pfizer PHQ-9, Pfizer GAD-7, 대한두통학회 GAD-7, and the government
> 별지14호 PHQ-9 form. §6's appendix now inline-quotes all 23 claimed-verbatim items (§1.2/§2.2/§3.2)
> — 0 item-text mismatches found, including PHQ-9 item 8 in both variants. 2 unrelated sourcing
> errors found and corrected loudly, not silently: §1.5's government-form license-footer overclaim,
> and §2.4/§A2b's now-unconfirmable GAD-7 Korean-PDF scoring-table citation (see §6's changelog for
> the full account). WHO-5/§4 and AUDIT-C/§5 untouched, out of scope this pass.

---

## How to read this file

- **Verbatim-confidence** column contains only the literal string `verbatim-from-source` — nothing
  else is permitted in an included row. If an item could not be verified verbatim, it is not in the
  table; it is listed in that instrument's **Gaps** subsection instead.
- **"Summary basis: abstract/secondary-summary only"** is stated explicitly wherever a cited paper's
  content came from a search-result summary rather than a full-text document I opened and read
  myself. Two Korean-population source papers for PHQ-9 (AUDIT-K's 1999 validation and AUDIT-C's
  2009 validity study) and one for AUDIT-C (Seo & Park 2015 for PHQ-9) were fetched and read in
  full as PDFs — those are marked accordingly.
- The **consolidated evidence appendix** at the end reproduces the actual quoted blocks extracted
  from each primary source, so a reviewer without web access can check every item/anchor/citation
  claim above against the quote itself.

---

## 1. PHQ-9 (depression, 9 items)

### 1.1 Chosen source + rationale

**Primary source (recommended for v1):** Pfizer's official screener portal, phqscreeners.com —
Korean translation, `PHQ9_Korean for Korea.pdf`. Retrieved 2026-07-13:
`https://www.phqscreeners.com/images/sites/g/files/g10060481/f/201412/PHQ9_Korean%20for%20Korea.pdf`.

**Rationale:** (a) this is the copyright holder's own sanctioned translation, carrying an explicit,
on-document free-use license (quoted in §1.5 and the appendix); (b) it is the translation basis
that Seo & Park (2015) — a Korean-population PHQ-9 validation study I read in full — explicitly
state they used, back-translated to English and confirmed identical by an independent native
speaker before administering it to 132 Korean migraine-clinic patients (see §1.3); (c) it keeps
provenance internally consistent with the GAD-7 source chosen in §2 (same portal, same license,
same anchor-wording family), which matters because PHQ-4 (§3) is compositionally built from the
first two items of each.

**Alternate found (legitimate, not chosen as primary):** the Korean government's own national
health-screening form — 보건복지부 (Ministry of Health and Welfare) 고시 "건강검진 실시기준"
[별지 제14호 서식] "정신건강검사 평가도구(PHQ-9)", amended 2025-01-01, canonical at the National Law
Information Center: `https://www.law.go.kr/LSW/flDownload.do?flSeq=148392427&flNm=...` (mirror I
was able to read successfully: `https://www.elandclinic.com/Download/Documents/PHQ-9.pdf`,
retrieved 2026-07-13). This is literally the form used in Korea's national general health
screening (일반건강검진) program today — arguably the single most "official" Korean PHQ-9 text in
active regulatory use. Its item wording differs from the Pfizer text at the sentence level (both
are faithful renderings of the same 9 DSM-based constructs; see §1.2 for both, verbatim) and its
response-anchor wording differs too ("전혀 아니다/여러날 동안/일주일 이상/거의 매일" vs Pfizer's
"전혀 방해받지 않았다/며칠 동안 방해받았다/7일 이상 방해받았다/거의 매일 방해받았다"). I did **not**
find an independently published psychometric validation paper tied specifically to this
government-form wording (as distinct from the general PHQ-9 literature) in this session — its
authority is regulatory/administrative, not psychometric-research-validated in what I could access.
**This is a live choice point, not resolved by me:** if the orchestrator/developer wants the item
bank to match what patients see on Korea's actual national health-screening form, the government
text is the better choice. Both are fully sourced below; picking between them is out of my scope
(no severity-band or item-selection decisions per the brief).

**Korean psychometric-validation lineage (per the brief's pointers), access status:**
- Choi HS, Choi JH, Park KH, Joo KJ, Ga H, Ko HJ, Kim SR (2007). "Standardization of the Korean
  Version of Patient Health Questionnaire-9 as a screening instrument for major depressive
  disorder." *J Korean Acad Fam Med* 28:114-119. Cutoff 8, Cronbach's α 0.852, sensitivity 90.9%,
  specificity 87% (per Seo & Park 2015's citation of it, which I read in full — see appendix).
  **I could not access this paper's own full text** (KCI/DBpia paywalled) to confirm which Korean
  translation (Pfizer vs government) it used. UNVERIFIED on translation identity.
- Park SJ et al. (2010). "한글판 우울증 선별도구(Patient Health Questionnaire-9, PHQ-9)의 신뢰도와
  타당도." *Korean J Anxiety Disorders* (대한불안의학회지). Located via search only; full text not
  accessed. UNVERIFIED on translation identity. Summary basis: search-result summary only.
- An JB et al. (2013) — located by title reference only in the brief; not independently found or
  read this session. UNVERIFIED, not cited further.
- Seo JG, Park SP (2015). "Validation of the Patient Health Questionnaire-9 (PHQ-9) and PHQ-2 in
  patients with migraine." *J Headache Pain* 16:65. doi:10.1186/s10194-015-0552-2. **Read in full**
  (open-access PDF). N=132 Korean migraine-clinic patients; explicitly used the phqscreeners.com
  Korean PHQ-9, back-translated and verified; optimal cutoff for this population = 7 (sensitivity
  79.5%, specificity 81.7%, PPV 64.6%, NPV 90.5%; Cronbach's α 0.894). This is a specialty
  (migraine-clinic), not general-primary-care, validation sample — flagged in §1.4.

### 1.2 Item table

| # | Korean item text (원문, verbatim) | Verbatim-confidence | Source |
|:--|:--|:--|:--|
| 1 | 일 또는 여가 활동을 하는 데 흥미나 즐거움을 느끼지 못함 | verbatim-from-source | Pfizer/phqscreeners.com Korean PHQ-9 PDF, retrieved 2026-07-13 (see appendix §A1) |
| 2 | 기분이 가라앉거나, 우울하거나, 희망이 없음 | verbatim-from-source | same |
| 3 | 잠이 들거나 계속 잠을 자는 것이 어려움, 또는 잠을 너무 많이 잠 | verbatim-from-source | same |
| 4 | 피곤하다고 느끼거나 기운이 거의 없음 | verbatim-from-source | same |
| 5 | 입맛이 없거나 과식을 함 | verbatim-from-source | same |
| 6 | 자신을 부정적으로 봄 - 혹은 자신이 실패자라고 느끼거나 자신 또는 가족을 실망시킴 | verbatim-from-source | same |
| 7 | 신문을 읽거나 텔레비전 보는 것과 같은 일에 집중하는 것이 어려움 | verbatim-from-source | same |
| 8 | 다른 사람들이 주목할 정도로 너무 느리게 움직이거나 말을 함. 또는 반대로 평상시보다 많이 움직여서, 너무 안절부절 못하거나 들떠 있음 | verbatim-from-source | same |
| 9 | 자신이 죽는 것이 더 낫다고 생각하거나 어떤 식으로든 자신을 해칠 것이라고 생각함 | verbatim-from-source | same |

**Alternate (government form) item table — also fully sourced, for the orchestrator's choice:**

| # | Korean item text (원문, verbatim) | Verbatim-confidence | Source |
|:--|:--|:--|:--|
| 1 | 일을 하는 것에 대한 흥미나 재미가 거의 없음 | verbatim-from-source | 건강검진 실시기준 [별지 제14호 서식], retrieved via elandclinic.com mirror 2026-07-13 (appendix §A3) |
| 2 | 가라앉은 느낌, 우울감 혹은 절망감 | verbatim-from-source | same |
| 3 | 잠들기 어렵거나 자꾸 깨어남, 혹은 너무 많이 잠 | verbatim-from-source | same |
| 4 | 피곤함, 기력이 저하됨 | verbatim-from-source | same |
| 5 | 식욕 저하 혹은 과식 | verbatim-from-source | same |
| 6 | 내 자신이 나쁜 사람이라는 느낌 혹은 내 자신을 실패자라고 느끼거나 나 때문에 나 자신이나 내 가족이 불행하게 되었다는 느낌 | verbatim-from-source | same |
| 7 | 신문을 읽거나 TV를 볼 때 집중하기 어려움 | verbatim-from-source | same |
| 8 | 남들이 알아챌 정도로 거동이나 말이 느림, 또는 반대로 너무 초조하고 안절부절 못해서 평소보다 많이 돌아다니고 서성거림 | verbatim-from-source | same |
| 9 | 나는 차라리 죽는 것이 낫겠다는 등의 생각 혹은 어떤 식으로든 스스로를 자해하는 생각들 | verbatim-from-source | same |

### 1.3 Response anchors + timeframe

**Pfizer text (primary):**
Timeframe/instruction: *"지난 2 주일 동안 당신은 다음의 문제들로 인해서 얼마나 자주 방해를 받았습니까?"*
Anchors: 전혀 방해 받지 않았다(0) / 며칠 동안 방해 받았다(1) / 7 일 이상 방해 받았다(2) / 거의 매일
방해 받았다(3). A follow-up functional-impairment item is also present (전혀 어렵지 않았다/약간
어려웠다/많이 어려웠다/매우 많이 어려웠다) but is not part of the 9 scored items.

**Government-form text (alternate):**
Timeframe/instruction: *"지난 2주 동안, 아래 나열되는 증상들에 얼마나 자주 시달렸습니까?"*
Anchors: 전혀 아니다(0) / 여러날 동안(1) / 일주일 이상(2) / 거의 매일(3).

Both source: appendix §A1/§A3.

### 1.4 Scoring confirmation

| Band | Implementation (`survey_scorer.py`) | Source finding | Verdict |
|:--|:--|:--|:--|
| 0-4 minimal | matches | Standard Kroenke et al. (2001) PHQ-9 5-band scale; cited as the reference scale by every Korean PHQ-9 source found this session (Seo & Park 2015 cites Kroenke 2001 directly as ref. 8) | CONFIRMED |
| 5-9 mild | matches | same | CONFIRMED |
| 10-14 moderate | matches | same | CONFIRMED |
| 15-19 moderately_severe | matches | same | CONFIRMED |
| 20-27 severe | matches | same | CONFIRMED |
| Item 9 ≥ 1 → critical/safety flag | matches | Item 9 in both Korean texts above is the DSM suicidal/self-harm ideation item; every source treats it as the safety-relevant item | CONFIRMED |

**Caveat:** I could not directly primary-source-verify the exact 5-band labels against a
Korean-government interpretive document — two attempts to open 국립정신건강센터's "2019/2020
정신건강검진도구 및 사용에 대한 표준지침" PDF (`ncmh.go.kr`) both failed (binary/undecodable in this
session's fetch tooling; not a confirmed absence of the document, a tooling limitation — see Open
items). A WebSearch-only (not directly read) snippet suggested a simplified 4-band public-facing
scheme exists somewhere in the Korean self-check ecosystem (0-4/5-9/10-19/20+, i.e. 10-19 merged)
— I am **not** treating this as a confirmed discrepancy since I never read a primary source stating
it; flagged as an open item for a future session with working access to that PDF.

Specialty-population caveat (Seo & Park 2015): their empirically optimal cutoff for *screening MDD
in migraine-clinic patients specifically* was 7, not the standard 10 (sensitivity 79.5%/specificity
81.7% at cutoff >7). This is a **cutoff for diagnostic screening**, not a restatement of the 5-band
severity scale, and applies to a specialty population — it does not contradict the band table above
and should not be conflated with it.

### 1.5 License note

**Fidelity correction (2026-07-13 appendix-completion pass):** this section previously stated that
"both Korean PHQ-9 texts carry, verbatim, on the document itself" the Pfizer license footer quoted
below. A fresh re-fetch of the government-form PDF (elandclinic.com mirror, appendix §A3) this
session found **no such footer, and no license/copyright text of any kind, anywhere in that
one-page document** — it ends at "점수 / 27" with nothing further. The original "both" claim was
inaccurate; corrected below, not silently.

The **Pfizer-sourced** Korean PHQ-9 carries, verbatim, on the document itself: *"Pfizer Inc.로부터
교육용 지원금을 받아 Robert L. Spitzer 박사, Janet B.W. Williams 박사, Kurt Kroenke 박사와 동료들에
의해 개발된 것임. 복제, 번역, 전시 또는 배포를 위해 허가가 필요하지 않음."* ("...developed with an
educational grant from Pfizer Inc. ... No permission is required to reproduce, translate, display,
or distribute.") Source: appendix §A1, re-confirmed via re-fetch 2026-07-13.

The **government-form** (별지 제14호) Korean PHQ-9 carries no explicit reproduction/license
statement anywhere in the fetched document. Its use basis is instead its status as an official
regulatory form published under 보건복지부고시 "건강검진 실시기준" — administrative/regulatory
authority, not a confirmed copyright waiver. UNVERIFIED whether a separate license applies to this
specific form; not confirmed either way from what was fetched.

### 1.6 Gaps

None for the 9 scored items or the primary anchor/timeframe text — full verbatim coverage from two
independent, directly-fetched sources. Open gap: Choi 2007 / Park 2010's own translation identity
vs the two texts above (UNVERIFIED, paywalled); the government interpretive-guideline PDF's 5-band
label text (tooling failure, not a confirmed absence).

---

## 2. GAD-7 (anxiety, 7 items)

### 2.1 Chosen source + rationale

**Primary source:** Pfizer's phqscreeners.com, Korean translation, `GAD7_Korean for Korea.pdf`.
Retrieved 2026-07-13:
`https://www.phqscreeners.com/images/sites/g/files/g10060481/f/201412/GAD7_Korean%20for%20Korea.pdf`.

**Rationale:** Ahn JK, Kim Y, Choi KH (2019). "The psychometric properties and clinical utility of
the Korean version of GAD-7 and GAD-2." *Frontiers in Psychiatry* 10:127.
doi:10.3389/fpsyt.2019.00127 — the largest, most rigorous Korean GAD-7 validation I located (N=1,157
community adults, structured-interview-confirmed diagnoses) — explicitly states it used "the
Korean version of the GAD-7 ... available on the Patient Health Questionnaire website," i.e. this
same phqscreeners.com text. **Summary basis: this paper was read only via a fetch-tool summary of
its content, not the full original PDF — its citation, cutoffs, and translation-source statement
are reported as the summarizing tool rendered them, not independently re-verified against the raw
PDF.** Findings reported (summary basis): GAD-7 ≥8 for GAD (sens 0.81/spec 0.85); GAD-7 ≥5 for any
anxiety disorder (sens 0.73/spec 0.74); no formal severity bands reported by this paper.

**Alternates found:**
- 대한두통학회 (Korean Headache Society), `headache.or.kr/pdf/GAD-7.pdf`, retrieved 2026-07-13 —
  clean, standard-quality Korean translation, textually close to the Pfizer text but not identical
  (see §2.2 vs the Pfizer table; anchor wording also differs slightly, §2.3). Not chosen as primary
  because I could not confirm which specific Korean-population validation study (if any) uses this
  exact wording, and it appears to be hosted for headache-clinic screening purposes rather than as
  a general psychiatric standard. Full item text quoted in the appendix (§A2b — cross-reference
  corrected 2026-07-13, was previously mislabeled §A2) as a legitimate alternate.
- `sbirtoregon.org` "GAD-7 Korean" PDF — **explicitly rejected, not used anywhere in this note.**
  This is a poor-quality, apparently machine-translated rendering: item 4 reads "트러블 이완" (a
  garbled, non-idiomatic rendering of "trouble relaxing" that is not natural Korean), and the
  response anchor for "not at all" is mistranslated as "천만에요" (literally "you're welcome," a
  translation error, not "전혀"). Quoted in the appendix (§A2b) only to document why it was
  rejected — this text must never be used as a source for item bank v1.

### 2.2 Item table

| # | Korean item text (원문, verbatim) | Verbatim-confidence | Source |
|:--|:--|:--|:--|
| 1 | 초조하거나 불안하거나 조마조마하게 느낀다 | verbatim-from-source | Pfizer/phqscreeners.com Korean GAD-7 PDF, retrieved 2026-07-13 (appendix §A2) |
| 2 | 걱정하는 것을 멈추거나 조절할 수가 없다 | verbatim-from-source | same |
| 3 | 여러 가지 것들에 대해 걱정을 너무 많이 한다 | verbatim-from-source | same |
| 4 | 편하게 있기가 어렵다 | verbatim-from-source | same |
| 5 | 너무 안절부절못해서 가만히 있기가 힘들다 | verbatim-from-source | same |
| 6 | 쉽게 짜증이 나거나 쉽게 성을 내게 된다 | verbatim-from-source | same |
| 7 | 마치 끔찍한 일이 생길 것처럼 두렵게 느껴진다 | verbatim-from-source | same |

### 2.3 Response anchors + timeframe

Timeframe/instruction: *"지난 2 주 동안 당신은 다음의 문제들로 인해서 얼마나 자주 방해를 받았습니까?
("✔"로 답을 나타내시오)"*
Anchors: 전혀 방해 받지 않았다(0) / 며칠 동안 방해 받았다(1) / 2 주 중 절반 이상 방해 받았다(2) /
거의 매일 방해 받았다(3). Source: appendix §A2.

Note the anchor wording at option 2 ("2주 중 절반 이상 방해받았다") differs from the Pfizer PHQ-9's
option-2 wording ("7일 이상 방해받았다") even though both are official Pfizer translations of the
same underlying "more than half the days" construct — this is reported as-is, verbatim per source,
not harmonized or corrected.

### 2.4 Scoring confirmation

**Fidelity correction (2026-07-13 appendix-completion pass):** this section and appendix §A2b
previously claimed a "For the clinician" scoring/interpretation table (bands + a Spitzer et al.
2006 citation) was read directly on "page 2" of the 대한두통학회 GAD-7 PDF. **A fresh re-fetch of
the identical URL this session (`http://www.headache.or.kr/pdf/GAD-7.pdf`) returns only 1 page** —
the Korean item table and a "총점/체크한 번호가 점수입니다" footer (appendix §A2b, updated) — **with
no clinician-facing scoring table, no band labels, and no citation anywhere in the document.**
Confirmed by explicitly requesting pages 1-3 from the fetched PDF; the tool reports only 1 page
exists. This session cannot determine whether the earlier dispatch read a document since replaced
at this URL or whether the claim was not actually grounded in the fetched content — either way it
is **not re-confirmable from the current source** and is retracted below rather than silently kept.

| Band | Implementation | Source finding | Verdict |
|:--|:--|:--|:--|
| 0-4 minimal | matches | International-convention basis only: Spitzer RL, Kroenke K, Williams JB, Löwe B. "A brief measure for assessing generalized anxiety disorder: the GAD-7." *Arch Intern Med.* 2006;166(10):1092-1097 — the GAD-7's original publication and its own reported 0-4/5-9/10-14/15-21 banding, a widely-cited standard reference; **not fetched or read in full this session** (citation-only basis). NOT confirmed against any Korean-language source (see correction above). | UNCONFIRMED-BY-KOREAN-SOURCE |
| 5-9 mild | matches | same | UNCONFIRMED-BY-KOREAN-SOURCE |
| 10-14 moderate | matches | same | UNCONFIRMED-BY-KOREAN-SOURCE |
| 15-21 severe | matches (score range) | same | UNCONFIRMED-BY-KOREAN-SOURCE |

No Korean-language primary source for the GAD-7 severity bands was confirmed this session. Per
ADR-033 decision 2, the band values themselves stay byte-unchanged regardless — this correction
concerns sourcing/evidence quality only, not a proposed value change.

### 2.5 License note

Same Pfizer footer as PHQ-9, verbatim: *"Pfizer Inc.로부터 교육용 지원금을 받아 Robert L. Spitzer
박사, Janet B.W. Williams 박사, Kurt Kroenke 박사와 동료들에 의해 개발된 것임. 복제, 번역, 전시 또는
배포를 위해 허가가 필요하지 않음."* Source: appendix §A2, directly confirmed.

### 2.6 Gaps

None for the 7 items, anchors, or timeframe — full verbatim coverage, directly fetched and now
appendix-quoted in full (§A2, cross-checked against §A2b). Open item: Ahn et al. (2019)'s exact
reported cutoffs are summary-basis only (not independently re-verified against the raw PDF). **New
gap opened 2026-07-13:** the severity-band Korean-source citation in §2.4 was retracted on
re-fetch (see §2.4/§A2b) — the bands now rest on the international Spitzer et al. (2006) convention
only, not a directly-read Korean-language source.

---

## 3. PHQ-4 (ultra-brief depression + anxiety, 4 items)

### 3.1 Chosen source + rationale

**No standalone official Korean PHQ-4 PDF was found.** Two direct URL attempts on
phqscreeners.com's naming pattern (`PHQ-4_Korean for Korea.pdf`, `PHQ4_Korean for Korea.pdf`) both
returned HTTP 404. No Korean-language academic source reproduced the PHQ-4's own item text as a
standalone instrument in what I could access.

**Chosen method (documented, cited, not fabricated):** Kim HW, Shin C, Lee SH, Han C (2021).
"Standardization of the Korean Version of the Patient Health Questionnaire-4 (PHQ-4)." *Clin
Psychopharmacol Neurosci* 19(1):104-111. doi:10.9758/cpn.2021.19.1.104. **Summary basis: read via
fetch-tool summary only, not the raw PDF.** This paper explicitly states the Korean PHQ-4
"consists of the first two items of the Korean version of the PHQ-9 ... and the first two items of
the Korean version of the GAD-7" — i.e. the instrument is not translated independently; it is
compositionally built from the two already-sourced instruments above. Every word of the 4 items
below is therefore `verbatim-from-source` against the Pfizer PHQ-9/GAD-7 PDFs already fetched in
§1-2; only the *composition rule* (which two items, in which order) is sourced from Kim et al.
2021 rather than from a standalone PHQ-4 document. This satisfies the fabrication-0 rule: no word
of Korean instrument text in the table below was invented — each item is copy-identical to an
already-verbatim-verified source, recombined per a documented, peer-reviewed method.

**Provenance choice matters here too:** because Kim et al. 2021 does not specify which Korean
GAD-7/PHQ-9 translation (Pfizer vs government) it composed from, I built the table below from the
Pfizer texts (§1-2's primary choice) for internal consistency. If the orchestrator later decides
the government-form texts should be primary for PHQ-9/GAD-7, the PHQ-4 items must be rebuilt from
the government-form's own items 1-2 (GAD-7 equivalent question isn't in the government PHQ-9 form —
a full government-lineage GAD-7 government form was not found this session, see §2 gaps) — flagged
as a dependency, not resolved here.

### 3.2 Item table

| # | Korean item text (원문, verbatim) | Subscale | Verbatim-confidence | Source |
|:--|:--|:--|:--|:--|
| 1 | 초조하거나 불안하거나 조마조마하게 느낀다 | anxiety (= GAD-7 item 1) | verbatim-from-source | GAD-7 item 1, quoted verbatim at appendix §A2; composition rule per Kim et al. 2021 (appendix §A4) |
| 2 | 걱정하는 것을 멈추거나 조절할 수가 없다 | anxiety (= GAD-7 item 2) | verbatim-from-source | GAD-7 item 2, quoted verbatim at appendix §A2; same composition rule |
| 3 | 일 또는 여가 활동을 하는 데 흥미나 즐거움을 느끼지 못함 | depression (= PHQ-9 item 1) | verbatim-from-source | PHQ-9 item 1, quoted verbatim at appendix §A1; composition rule per Kim et al. 2021 (appendix §A4) |
| 4 | 기분이 가라앉거나, 우울하거나, 희망이 없음 | depression (= PHQ-9 item 2) | verbatim-from-source | PHQ-9 item 2, quoted verbatim at appendix §A1; same composition rule |

### 3.3 Response anchors + timeframe

Per Kim et al. 2021 (summary basis): *"All items are scored from 0 to 3 depending on the frequency
patients have been bothered by the symptoms over the preceding two weeks."* This matches the
Pfizer GAD-7/PHQ-9 anchor conventions already sourced in §1.3/§2.3 (전혀 방해받지 않았다(0)/며칠
동안 방해받았다(1)/... 거의 매일 방해받았다(3), with the option-2 wording difference between the two
parent instruments noted in §2.3 carried through unresolved here (item 1-2 use GAD-7's "2주 중
절반 이상," item 3-4 use PHQ-9's "7일 이상" — I did not harmonize this, it is inherited verbatim
from each parent instrument per the composition rule).

### 3.4 Scoring confirmation

| Band / rule | Implementation | Source finding | Verdict |
|:--|:--|:--|:--|
| 0-2 normal / 3-5 mild / 6-8 moderate / 9-12 severe | matches the standard international PHQ-4 (Kroenke, Spitzer, Williams, Löwe 2009) band structure | Kim et al. 2021 (summary basis) reports a single optimal "flag" cutoff of ≥6 (95.7th percentile) in a Korean psychiatric-outpatient sample (N=116), not an independent validation of all 4 band edges | CONFIRMED for structure; the Korean paper's own reported flag point (≥6) falls exactly on the implementation's moderate/severe boundary, consistent but not an independent full-band validation |
| anxiety_sub = items 1+2, depression_sub = items 3+4 | matches | Kim et al. 2021 explicitly confirms this is "the first two items of ... GAD-7" (anxiety) + "the first two items of ... PHQ-9" (depression) | CONFIRMED |
| total ≥ 6 → clinician_review | matches | Kim et al. 2021's own reported "yellow flag" cutoff is ≥6 | CONFIRMED — direct match |

### 3.5 License note

Composed entirely from Pfizer-licensed text (§1.5, §2.5) — same free-use terms apply by
construction, since every word in the PHQ-4 table traces to the Pfizer PHQ-9/GAD-7 documents.

### 3.6 Gaps

No standalone official Korean PHQ-4 document found (2 direct-URL attempts, both 404). Kim et al.
2021's own paper was read via summary only, not the raw PDF — its band-cutoff and citation details
above are summary-basis and should be re-verified against the primary PDF before being treated as
fully confirmed in a future session.

---

## 4. WHO-5 (well-being, 5 items)

### 4.1 Chosen source + rationale

**No verbatim Korean item text could be obtained across two sessions (2026-07-13, both dispatches).**
This is reported honestly as a full gap for the item table — nothing is included below.

**Retry 2026-07-13 (second dispatch) — newly attempted, newly found:**
- **Identified the primary underlying Korean-language source paper**, previously known only via its
  English-language sibling (Moon et al. 2014, below): Kim HJ, Moon YS, Son BK, Lee SK, Noh HJ, Kim DH
  (2010). "지역사회에 거주하고 있는 노인의 우울증과 삶의 질을 평가하는 도구로 한국판 WHO-5의 유용성"
  ["The Utility of Korean Version of the WHO Five Well-Being Index in Evaluating Depressive Symptoms
  and Quality of Life in the Aged Dwelling in Community"]. *노인정신의학* (J Korean Geriatric
  Psychiatry) 14(2):90-96. Same N=244, Gangwon Province community-dwelling-elderly sample as Moon et
  al. 2014, overlapping authorship (Kim HJ, Moon YS, Kim DH in both) — almost certainly the original
  Korean-language report of the same study, with Moon et al. 2014 as its English-language companion
  publication. **Full text still not accessible**: KCI's own "KCI 원문 내려받기" button is gated
  despite RISS displaying a "무료"/free full-text badge for it — clicking through returns an
  institutional-credential wall, not a PDF; DBpia shows abstract only, paywalled beyond that.
  Directly fetched (not summary-basis) from three independent bibliographic-database pages this
  session — KCI's own article view, DBpia, and RISS — all three display the **same English abstract
  sentence verbatim**: *"The total score of WHO-5 below 13 indicates low well-being"* (appendix
  §A9b). This upgrades the cutoff evidence from "summary basis only" (prior session) to "directly
  read, on the primary source's own abstract page, independently converging across 3 database
  mirrors" — still short of reading the paper's methods/results section, but no longer secondhand.
- **`psykiatri-regionh.dk`** (the WHO-5's official host) — **2 more fetch attempts timed out** this
  session (the References page, and a guessed `WHO5_Korean.pdf` direct URL), bringing the
  cross-session total to **5/5 timeouts**. This is now an established dead end for this tooling
  environment, not a fluke — do not keep retrying the bare URL; a working access path (different
  tool/session/network) would be needed, or ask the user if they hold a cached copy. `web.archive.org`
  was tried as a bypass and is **categorically blocked** for WebFetch in this environment ("Claude
  Code is unable to fetch from web.archive.org") — a tooling limitation, not worth retrying.
- **국립정신건강센터 (NCMH) "정신건강 검진도구 및 사용에 대한 표준지침"** (the government standard
  guide reported to include WHO-5 among its screening tools) — tried via two additional routes beyond
  the earlier-session `ncmh.go.kr` jsp-viewer dead end: (a) `nongsaro.go.kr`'s mirrored copy of the
  same PDF — its download link is JavaScript-triggered (`href="#none"`), no fetchable direct URL
  exposed in the rendered page; (b) the `ncmh.go.kr` board page itself — same problem, the attachment
  is named in the page but WebFetch's markdown conversion strips the actual servlet URL, reporting
  only the filename and download count. **Confirmed dead end via three independent routes now**
  (jsp-viewer, nongsaro mirror, direct board page) — the consistent blocker is that these Korean
  government CMSs serve attachments via JS-triggered handlers or session-scoped servlets that
  WebFetch cannot resolve to a plain-fetchable URL, not that the document doesn't exist.
- Broad Korean-language searches for the item text itself (candidate phrasings like "명랑하고 기분이
  좋았다", "차분하고 편안하게"; search terms combining "WHO-5" with "부록"/"문항"/"자가진단"; searches
  scoped to koreascience.kr) surfaced **no Korean academic paper, self-test site, or public-health
  form that reproduces the WHO-5's own item text** this session. One promising-looking lead (a
  가정의학회지 IPAQ validation PDF, `kjfm.or.kr/upload/pdf/Jkafm028-07-06.pdf`) was fetched and read in
  full but turned out to be about a different instrument (International Physical Activity
  Questionnaire, not WHO-5) — a false lead, documented here so a future session does not re-fetch it.

**What was already known (prior session, unchanged):**
- WHO's own CDN (`cdn.who.int/media/docs/default-source/mental-health/...`), which hosts several
  confirmed language files (Chinese, Finnish, Polish, Spanish, French, German, Dutch, Arabic,
  Japanese, Danish, Hebrew, Slovenian) at a consistent URL-naming pattern — a Korean file at the
  same pattern returned HTTP 404.
- Moon YS, Kim HJ, Kim DH (2014). "The relationship of the Korean version of the WHO Five
  Well-Being Index with depressive symptoms and quality of life in the community-dwelling elderly."
  *Asian J Psychiatry* 9:26-30. doi:10.1016/j.ajp.2013.12.014 — the English-language sibling of the
  2010 Korean paper above (same sample). Full text remains inaccessible: PubMed's own page confirms
  directly this session that **no PMC deposit and no free full-text link exists** for this article;
  ScienceDirect/ClinicalKey are paywalled. OpenAlex's and Semantic Scholar's own APIs were queried
  directly this session for an alternate open-access PDF location — both report **no OA PDF URL
  available** (OpenAlex: `best_oa_location`/`primary_location` PDF URLs both null; the work's only
  "OA" location is the paywalled ScienceDirect DOI landing page itself, under a CC-BY-NC-ND license
  that would restrict redistribution even if the PDF were reached).
- The Korean phrase "안녕지수" — a plausible-sounding Korean name for "well-being index" — is
  **already in wide use for a different, unrelated instrument** (Seoul National University Happiness
  Research Center / Kakao's real-time "Annyeong Index" happiness-tracking survey). This is a
  naming-collision risk: if item bank v1 ever labels the WHO-5 "안녕지수" in Korean, that label will
  be ambiguous with the SNU/Kakao instrument; worth flagging to whoever authors v1 Korean labels.

### 4.2 Item table

**ABSENT.** No item, in Korean or otherwise, is included per the fabrication-0 rule. All 5 items
are gaps (§4.6).

### 4.3 Response anchors + timeframe

**ABSENT — gap.** I know the *scoring mechanics* (see §4.4) but not the Korean-language anchor
wording or instruction/timeframe text for any of the 5 items. Not fabricated, not reconstructed.

### 4.4 Scoring confirmation

| Rule | Implementation | Source finding | Verdict |
|:--|:--|:--|:--|
| percentage = raw × 4 | matches | This is the WHO-5's universally standard transform (raw 0-25 → percentage 0-100), confirmed by every WHO-5 source touched this session including the general (non-Korean-specific) WHO-5 documentation | CONFIRMED |
| raw ≤ 13 → low_wellbeing/further_assessment | off-by-one from source, boundary now CONFIRMED-discrepant | Directly fetched (not summary-basis) this session from three independent primary-source database pages (KCI, DBpia, RISS — appendix §A9b) — all three display the identical English abstract sentence, verbatim, for **both** the 2010 Korean paper and (per prior-session PubMed/ScienceDirect abstract text) its 2014 English sibling: *"The total score of WHO-5 below 13 indicates low well-being."* "Below 13" = raw < 13 = raw ≤ 12 is flagged low-wellbeing; the implementation's `raw <= 13` additionally flags raw = 13 exactly, which the Korean-validated cutoff would **not** flag. This is a real, sourced off-by-one, not a paraphrase artifact — confirmed by 3 independently-fetched mirrors of the same primary-source abstract text. | CONFIRMED DISCREPANCY (off-by-one at the boundary: implementation flags raw=13 as low-wellbeing; source cutoff does not) — reporting only, not deciding a fix, per this note's scope |

### 4.5 License note

Summary basis only (not independently confirmed against a primary licensing-terms page — both
fetch attempts on the terms page itself timed out): pre-2024 WHO-5 translations were originally
published by the Psychiatric Centre North Zealand (Copenhagen, Denmark) and made available for
non-commercial clinical/research use; in 2024 the Centre reportedly assigned copyright in the
WHO-5 to WHO itself, described in search summaries as intended to enable WHO to publish it as an
"open access product." I could not confirm the precise licensing terms (e.g. whether commercial use
requires permission, whether translation/redistribution is unrestricted the way Pfizer's PHQ family
explicitly is) from a primary source this session.

### 4.6 Gaps

**Full item table gap — still open after retry 2026-07-13.** All 5 WHO-5 items, their Korean text,
and the response anchor/instruction/timeframe wording remain ABSENT from this note. This is the
single largest gap in this deliverable, now confirmed robust: `psykiatri-regionh.dk` (the official
host) is 5/5 timeouts across two sessions; the two Korean-population validation papers that would
most plausibly reproduce the item text (Kim et al. 2010, 노인정신의학 14(2):90-96; Moon et al. 2014,
*Asian J Psychiatry* 9:26-30) are both abstract-only accessible — gated by KCI/DBpia and
ScienceDirect/ClinicalKey respectively, with no PMC deposit and no OA PDF location per direct
OpenAlex/Semantic Scholar API queries; the Korean government's own standard-tool-guide PDF
(국립정신건강센터, likely reproducing WHO-5 as one of several screening instruments) is blocked by
JS-triggered download handlers on every route tried (jsp-viewer, nongsaro.go.kr mirror, direct board
page); and broad Korean-language web search for the item text itself surfaced no self-test site,
public-health form, or academic appendix that reproduces it. What DID improve this retry: the
precise primary-source citation (Kim et al. 2010) and a directly-fetched (not summary-basis),
triply-converging confirmation of the raw<13 low-wellbeing cutoff, now stated as a confirmed
off-by-one discrepancy against the implementation rather than an unresolved paraphrase question
(§4.4). **Recommended next step for a future session:** this is not a "try again with the same
tool" gap — it needs either (a) a different fetch path for `psykiatri-regionh.dk` (proxy, different
session/network, or a human manually downloading and pasting the content), (b) institutional/KCI
credential access to Kim et al. 2010's full text, or (c) asking the user directly whether they hold
a copy of the Korean WHO-5 from prior clinical/research use — repeating the same WebFetch attempts
on the same URLs is very unlikely to succeed a 6th/3rd/4th time.

---

## 5. AUDIT-C (alcohol use, 3 items)

### 5.1 Chosen source + rationale

**Primary source for item text:** SBIRT Oregon's Korean AUDIT translation (the full 10-item AUDIT;
items 1-3 constitute AUDIT-C), retrieved 2026-07-13:
`http://www.sbirtoregon.org/wp-content/uploads/AUDIT-Korean-pdf.pdf`. This is a clean,
professionally produced Korean translation (unlike the same site's garbled GAD-7-Korean file,
§2.1) funded by a US state SBIRT (Screening, Brief Intervention, Referral to Treatment) grant
program, explicitly citing the WHO AUDIT manual (Babor, Higgins-Biddle, Saunders, Monteiro (2001).
*The Alcohol Use Disorders Identification Test: Guidelines for Use in Primary Care*, 2nd ed. WHO
Dept. of Mental Health and Substance Dependence, Geneva) as its instrument source.

**Critical translation-version-identity caveat (per this note's constraint (d)):** this SBIRT
Oregon text's item 3 asks about "4잔 이상" (4-or-more standard drinks) in a single occasion, and its
item 1-2 response options are calibrated to explicitly-stated **US** standard-drink sizes (12oz
beer / 5oz wine / 1.5oz spirits, printed on the document itself). This is the US-adapted AUDIT-C
(Bush, Kivlahan, McDonell, Fihn, Bradley 1998) binge-item convention, not the original WHO AUDIT's
"6 or more drinks" item-3 framing, and — more importantly for this project — **not necessarily
identical to the item wording used by the two Korean-population AUDIT-C validation studies cited in
§5.4**, whose surrounding literature describes the Korean AUDIT-K's binge item as calibrated to
Korean drink units ("소주 1병 또는 맥주 4병 이상," i.e. ~6 Korean standard units, per the
introduction of Seong et al. 2009, which I read in full — see appendix §A6). **I could not retrieve
the byte-exact item wording of the actual instrument Kim et al. (1999) or Seong et al. (2009) used**
— their published papers report methodology and results but the item-text itself was not
reproduced in the article pages I could access (both were read in full as PDFs; neither includes an
appendix with the Korean question text). This is an open, disclosed gap: **the item table below is
verbatim-sourced and translation-quality-checked, but is not confirmed to be the same translation
instance used in the Korean-population cutoff studies that inform §5.4's scoring discussion.**

**Alternates found, not used:** `sbirtoregon.org`'s AUDIT-Korean PDF was the only source that
yielded clean, complete, verbatim item text within this session's effort budget. A Korean
self-test aggregator site (dsr5000.com) shows a full 10-item AUDIT-K with plausible-looking item
text and response categories, but as a non-authoritative self-test aggregator (not a
government/WHO/peer-reviewed primary source) it is **not used** as a citation source here — noted
for completeness, not included in the item table.

### 5.2 Item table

| # | Korean item text (원문, verbatim) | Verbatim-confidence | Source |
|:--|:--|:--|:--|
| 1 | 알코올 음료를 얼마나 자주 마십니까? | verbatim-from-source | SBIRT Oregon Korean AUDIT PDF, retrieved 2026-07-13 (appendix §A5) |
| 2 | 술을 마실 때 보통 알코올 음료를 몇 잔 정도 마십니까? | verbatim-from-source | same |
| 3 | 한 번에 4 잔 이상을 얼마나 자주 마십니까? | verbatim-from-source | same |

### 5.3 Response anchors + timeframe

Item 1 anchors: 마시지 않음(0) / 월 1회 또는 미만(1) / 월 2~4회(2) / 주 2~3회(3) / 주 4회 이상(4).
Item 2 anchors: 0~2잔(0) / 3~4잔(1) / 5~6잔(2) / 7~9잔(3) / 10잔 이상(4).
Item 3 anchors: 없음(0) / 월 1회 미만(1) / 월 1회(2) / 주 1회(3) / 매일 또는 거의 매일(4).

There is no single "지난 2주"-style instruction line covering items 1-3 the way PHQ-9/GAD-7 do —
AUDIT/AUDIT-C items 1-2 ask about current/typical drinking pattern with no explicit lookback window
stated on the item itself; item 3 similarly has no explicit window on the item text (the "past
year" framing appears explicitly only on AUDIT's items 4-10, which are not part of AUDIT-C). The
document's general intro line is: *"알코올 섭취는 귀하의 건강과 복용하는 일부 약에 영향을 미칠 수
있습니다. 귀하께 최선의 치료를 제공할 수 있도록 아래의 질문에 답해 주십시오."* A "1잔의 기준"
(standard-drink definition) block precedes the items: *"1 잔의 기준: 12 온스(355mL) 맥주 / 5
온스(148mL) 와인 / 1.5 온스(44mL) 독주(1 잔)"* (source: appendix §A5; note the OCR/extraction in
this session rendered "12 온스" with an extra leading "1" as "112 온스" in one pass — the corrected
reading, cross-checked against the standard US drink definition and the image's separate "BEER"
icon context, is 12 온스/355mL, the standard US beer serving size; flagged here rather than silently
corrected, since exact OCR fidelity matters for this deliverable).

### 5.4 Scoring confirmation

**Implementation:** `patient_sex == "female"` → threshold 3; else (male/unknown) → threshold 4;
`total >= threshold` → `hazardous_drinking`.

**Korean-population evidence found (both read in full as PDFs, not summary basis):**

| Study | Population | Criterion | AUDIT-C optimal cutoff found |
|:--|:--|:--|:--|
| Seong JH, Lee CH, Do HJ, Oh SW, Lym YL, Choi JK, Joh HK, Kweon KJ, Cho DY (2009). "일차진료에서 문제음주자 선별을 위한 AUDIT-C의 타당도 조사." *Korean J Fam Med* 30(9):695-702. doi:10.4082/kjfm.2009.30.9.695 | N=302, Korean men only, university-hospital patients with drinking history (2007-2008) | AUDIT-K-defined "problem drinking" | ≥8 (sensitivity 82%, specificity 76%). No female cutoff derived (male-only study). |
| Woo SM, Jang OJ, Choi HK, Lee YR (2017). "위험음주자 선별을 위한 한국판 알코올사용장애 선별검사(AUDIT-K), 알코올 소비 점수(AUDIT-C), 3번 문항(AUDIT3)의 유용성과 최적 절단값." *J Korean Acad Addict Psychiatry* 21(2):62-67. doi:10.37122/kaap.2017.21.2.62. **Summary basis only** (fetched via a scholarly-portal summary page, not the raw PDF). | N=509 (265 men, 244 women), online community survey (Feb 2016) | NIAAA hazardous-drinking definition | Men: 7. Women: 6. |

Both Korean-population studies report AUDIT-C optimal cutoffs **substantially higher** than the
current implementation's 4 (male) / 3 (female) — roughly double for men (7-8 vs 4) and roughly
double for women (6 vs 3, though the only female-specific Korean figure found, 6, is summary-basis
only and not independently re-verified). Seong et al. (2009) explicitly discuss *why* their
Korean-derived cutoff is higher than the commonly-cited international AUDIT-C conventions they
themselves cite (US: male ≥4/female ≥2 per Bush et al. 1998; Spain: male ≥5/female ≥4) — they
attribute it to their diagnostic criterion being the Korean AUDIT-K's own screening threshold (≥12
for "problem drinking" on the full 10-item AUDIT-K, itself higher than the international AUDIT's
≥8), not necessarily a true population difference in drinking-related harm at a given consumption
level; they explicitly recommend future research to establish independently-derived Korean
risk-drinking criteria and note "AUDIT-C ... 역시 본 연구에서 제시하는 점수보다 낮은 점수를 적용하는
것도 어느 정도 타당할 것으로 사료된다" (applying a somewhat lower cutoff than this study's finding
may also be reasonably valid) — appendix §A6.

**I am reporting this evidence, not deciding a change.** This is a discrepancy meeting the brief's
explicit instruction to flag for orchestrator disposition — the direction (Korean-population data
suggests higher AUDIT-C thresholds than current implementation) is consistent across both studies
found, but the exact number to use (7? 8? gender-specific vs unified?) is contested even within the
Korean literature itself, and neither source's underlying item translation is confirmed identical
to the SBIRT Oregon text chosen as primary in §5.1.

**Response range (0-4 per item, max 12):** CONFIRMED correct — matches both the SBIRT Oregon item
text (5-point 0-4 scale per item) and Seong et al. (2009)'s explicit description ("1,2번 문항의
응답점수는 '전혀 안 마신다'가 0점, '일주일에 4번 이상'이 4점으로 계산되고 ... AUDIT-C 총점은 최대
12점"), which matches `survey_scorer.py`'s own `0 <= responses[i] <= 4` validation exactly.

### 5.5 License note

WHO (Saunders JB, Aasland OG, Babor TF, de la Fuente JR, Grant M. 1993. "Development of the
alcohol use disorders identification test (AUDIT)..." *Addiction* 88:791-804; Babor, Higgins-Biddle,
Saunders, Monteiro 2001, *AUDIT: Guidelines for Use in Primary Care*, 2nd ed., WHO). I could **not**
find an explicit "no permission required" statement for AUDIT the way Pfizer states it verbatim on
every PHQ-family document (§1.5, §2.5) — UNVERIFIED on the precise licensing wording. The
instrument's status as a WHO public-health guideline document, and its free redistribution by a US
state government program (SBIRT Oregon) and multiple Korean public-health-center self-test pages
found during this session's searches, indicates open public-health use is standard practice, but
this is an inference from usage pattern, not a confirmed license-text quote.

### 5.6 Gaps

Byte-exact item wording of the specific instrument used by Kim et al. (1999) and Seong et al.
(2009) — the two Korean-population-validated AUDIT-K/AUDIT-C sources — was not retrieved (paywalled
methodology sections describe response categories and cutoffs but the papers I could access do not
reproduce a Korean-text item appendix). The SBIRT-Oregon-sourced item text used above is a
legitimate, verbatim, quality-checked Korean AUDIT-C translation, but its identity-match to the
Korean-validated instrument is unconfirmed. Explicit WHO AUDIT licensing-terms text (equivalent to
Pfizer's) was not located.

---

## 6. Consolidated evidence appendix

> **Changelog (2026-07-13, appendix-completion pass, CVR-016 condition 4 / ADR-033 decision 4):**
> re-fetched the Pfizer PHQ-9 PDF, Pfizer GAD-7 PDF, 대한두통학회 GAD-7 PDF, and the government
> 별지14호 PHQ-9 form (elandclinic.com mirror) and added full inline quotes for PHQ-9 items 3-8
> (both Pfizer and government-form variants, §A1/§A3), GAD-7 items 2-6 (Pfizer primary, §A2, plus
> the 대한두통학회 alternate as cross-verification, §A2b), and PHQ-4's derived rows now traced to
> those same quotes (§A4, §3.2). All 23 item strings previously tabled matched the fresh re-fetch
> byte-for-byte — **including PHQ-9 item 8 in both variants**, the item this whole v1 mission exists
> to verify (CVR-015 Finding 1 / CVR-016 Finding 2). **Two unrelated fidelity corrections found and
> applied, not silently fixed:** (1) §1.5 wrongly claimed the government PHQ-9 form carries the same
> Pfizer license footer as the Pfizer text — re-fetch shows the government form's single page has no
> such footer or any license text; corrected in §1.5 and §A3. (2) §2.4/§A2b previously quoted a
> "For the clinician" GAD-7 scoring/interpretation table attributed to "page 2" of the 대한두통학회
> PDF — re-fetching the identical URL this session (confirmed via an explicit `pages="1-3"` request)
> shows the document has only 1 page, with no such table anywhere in it. That quote is retracted;
> §2.4 is downgraded to international-convention-only sourcing for the GAD-7 bands (the bands
> themselves are unchanged per ADR-033 decision 2 — this is a sourcing-evidence correction, not a
> value change).

Each block below is the actual extracted text this note's claims are based on. Sources fetched and
read in full as PDFs are marked **[full PDF read]**; sources reported from a fetch-tool's summary
of a page (not the raw document text) are marked **[summary basis]**.

### §A1 — Pfizer/phqscreeners.com Korean PHQ-9 **[full PDF read; re-fetched and re-verified 2026-07-13]**

Retrieved 2026-07-13 (original) and re-fetched 2026-07-13 (this pass, byte-identical result):
`https://www.phqscreeners.com/images/sites/g/files/g10060481/f/201412/PHQ9_Korean%20for%20Korea.pdf`

> 환자 건강 질문지-9 (PHQ-9)
> 지난 2 주일 동안 당신은 다음의 문제들로 인해서 얼마나 자주 방해를 받았습니까? ("✔"로 답을
> 나타내시오)
> [anchors] 전혀 방해 받지 않았다(0) / 며칠 동안 방해 받았다(1) / 7 일 이상 방해 받았다(2) / 거의
> 매일 방해 받았다(3)
> 1. 일 또는 여가 활동을 하는 데 흥미나 즐거움을 느끼지 못함 [0 1 2 3]
> 2. 기분이 가라앉거나, 우울하거나, 희망이 없음 [0 1 2 3]
> 3. 잠이 들거나 계속 잠을 자는 것이 어려움, 또는 잠을 너무 많이 잠 [0 1 2 3]
> 4. 피곤하다고 느끼거나 기운이 거의 없음 [0 1 2 3]
> 5. 입맛이 없거나 과식을 함 [0 1 2 3]
> 6. 자신을 부정적으로 봄 - 혹은 자신이 실패자라고 느끼거나 자신 또는 가족을 실망시킴 [0 1 2 3]
> 7. 신문을 읽거나 텔레비전 보는 것과 같은 일에 집중하는 것이 어려움 [0 1 2 3]
> 8. 다른 사람들이 주목할 정도로 너무 느리게 움직이거나 말을 함. 또는 반대로 평상시보다 많이
>    움직여서, 너무 안절부절 못하거나 들떠 있음 [0 1 2 3]
> 9. 자신이 죽는 것이 더 낫다고 생각하거나 어떤 식으로든 자신을 해칠 것이라고 생각함 [0 1 2 3]
> Pfizer Inc.로부터 교육용 지원금을 받아 Robert L. Spitzer 박사, Janet B.W. Williams 박사, Kurt
> Kroenke 박사와 동료들에 의해 개발된 것임. 복제, 번역, 전시 또는 배포를 위해 허가가 필요하지 않음.

**Fidelity check (2026-07-13 re-fetch):** all 9 items, the anchor header, and the license footer
are byte-identical to §1.2's primary table and §1.5's license quote — no corrections required for
this source. Item 8, the subject of CVR-015 Finding 1 / CVR-016 Finding 2, is confirmed exact:
*"다른 사람들이 주목할 정도로 너무 느리게 움직이거나 말을 함. 또는 반대로 평상시보다 많이
움직여서, 너무 안절부절 못하거나 들떠 있음."*

### §A2 — Pfizer/phqscreeners.com Korean GAD-7 **[full PDF read; re-fetched and re-verified 2026-07-13]**

Retrieved 2026-07-13 (original) and re-fetched 2026-07-13 (this pass, byte-identical result):
`https://www.phqscreeners.com/images/sites/g/files/g10060481/f/201412/GAD7_Korean%20for%20Korea.pdf`

> GAD-7
> 지난 2 주 동안 당신은 다음의 문제들로 인해서 얼마나 자주 방해를 받았습니까? ("✔"로 답을
> 나타내시오)
> [anchors] 전혀 방해 받지 않았다(0) / 며칠 동안 방해 받았다(1) / 2 주 중 절반 이상 방해 받았다(2)
> / 거의 매일 방해 받았다(3)
> 1. 초조하거나 불안하거나 조마조마하게 느낀다 [0 1 2 3]
> 2. 걱정하는 것을 멈추거나 조절할 수가 없다 [0 1 2 3]
> 3. 여러 가지 것들에 대해 걱정을 너무 많이 한다 [0 1 2 3]
> 4. 편하게 있기가 어렵다 [0 1 2 3]
> 5. 너무 안절부절못해서 가만히 있기가 힘들다 [0 1 2 3]
> 6. 쉽게 짜증이 나거나 쉽게 성을 내게 된다 [0 1 2 3]
> 7. 마치 끔찍한 일이 생길 것처럼 두렵게 느껴진다 [0 1 2 3]
> (For office coding: Total Score T____ = ____ + ____ + ____ )
> Pfizer Inc.로부터 교육용 지원금을 받아 Robert L. Spitzer 박사, Janet B.W. Williams 박사, Kurt
> Kroenke 박사와 동료들에 의해 개발된 것임. 복제, 번역, 전시 또는 배포를 위해 허가가 필요하지 않음.

**Fidelity check (2026-07-13 re-fetch):** all 7 items, the anchor header, and the license footer
are byte-identical to §2.2's item table, §2.3's anchor quote, and §2.5's license quote — no
corrections required for this source.

### §A2b — 대한두통학회 (Korean Headache Society) Korean GAD-7 **[full PDF read; re-fetched 2026-07-13]** (alternate, not primary)

Retrieved 2026-07-13 (original) and re-fetched 2026-07-13 (this pass): `http://www.headache.or.kr/pdf/GAD-7.pdf`

**Fidelity correction (2026-07-13 re-fetch):** this block previously continued with a quoted "For
the clinician — Scoring and Interpretation" table (bands + a Spitzer et al. 2006 citation),
attributed to "page 2" of this same PDF. **A fresh re-fetch of this exact URL this session found
only 1 page — the item table below — with no clinician-scoring section, no band labels, and no
citation anywhere in the document** (confirmed by explicitly requesting pages 1-3; the tool reports
1 page exists). That quoted content is retracted here as not re-confirmable from the current
source; see §2.4 for the corresponding correction to the scoring-confirmation table.

> Generalized Anxiety Disorder-7 (GAD-7)
> # 지난 2주일 동안 당신은 다음의 문제들로 인해서 얼마나 자주 방해를 받았는지 해당번호에 표시(V)해
> 주세요.
> [anchors] 전혀 방해 받지 않았다(0) / 며칠 동안 방해 받았다(1) / 7일 이상 방해 받았다(2) / 거의
> 매일 방해 받았다(3)
> 1) 초조하거나 불안하거나 조마조마하게 느낀다 [0 1 2 3]
> 2) 걱정하는 것을 멈추거나 조절할 수가 없다 [0 1 2 3]
> 3) 여러 가지 것들에 대해 걱정을 너무 많이 한다 [0 1 2 3]
> 4) 편하게 있기가 어렵다 [0 1 2 3]
> 5) 너무 안절부절못해서 가만히 있기가 힘들다 [0 1 2 3]
> 6) 쉽게 짜증이 나거나 쉽게 성을 내게 된다 [0 1 2 3]
> 7) 마치 끔찍한 일이 생길 것처럼 두렵게 느껴진다 [0 1 2 3]
> 총점 [ ]점
> ※ 체크한 번호가 점수입니다.

**Cross-check value (positive):** all 7 items in this alternate translation are word-for-word
identical to the Pfizer primary text (§A2) — only the anchor wording differs (this source uses
"7일 이상 방해 받았다" for option 2, matching the Pfizer PHQ-9 convention, vs. Pfizer GAD-7's "2주
중 절반 이상 방해 받았다"; both already reported, not harmonized, per §2.3). This is independent
corroboration of the Pfizer GAD-7 item text from a second, differently-hosted Korean source — it
just cannot corroborate the severity bands (see correction above).

### §A2c — sbirtoregon.org Korean GAD-7 **[full PDF read] — REJECTED, quoted only to document rejection**

Retrieved 2026-07-13: `https://www.sbirtoregon.org/wp-content/uploads/GAD-7-Korean-pdf.pdf`

> 지난 2주 동안 다음과 같은 문제로 얼마나 자주 괴로워하셨습니까?
> [anchor labels, verbatim as extracted:] 천만에요 / 며칠 / 하루의 절반 이상 / 거의 매일
> 4. 트러블 이완 [0 1 2 3]

The anchor "천만에요" (literally "you're welcome") and item 4's "트러블 이완" are clear translation
defects (not idiomatic Korean for "not at all" / "having trouble relaxing"). **This source is
excluded from the item table and must not be used for item bank v1.**

### §A3 — Korean government health-screening PHQ-9 form **[full PDF read; re-fetched and re-verified 2026-07-13]** (elandclinic.com mirror)

Retrieved 2026-07-13 (original) and re-fetched 2026-07-13 (this pass, byte-identical result):
`https://www.elandclinic.com/Download/Documents/PHQ-9.pdf`. Canonical source per search:
국가법령정보센터 (law.go.kr), 건강검진 실시기준 [별지 제14호 서식], amended 2025-01-01.

> ■ 건강검진 실시기준 [별지 제14호 서식]
> 정신건강검사 평가도구(PHQ-9)
> 한글판 Patient Health Questionnaire-9: PHQ-9
> 본 설문은 우울한 정도를 스스로 알아보기 위한 것입니다. 이 질문들이 확정된 진단을 위한 것은
> 아니지만 높은 점수가 나왔을 경우에는 우울증의 가능성이 높으므로, 더 정확한 평가를 위해서
> 병원에서 진료를 받아볼 것을 추천합니다. 지난 2주 동안, 아래 나열되는 증상들에 얼마나 자주
> 시달렸습니까?
> [anchors] 전혀 아니다(0) / 여러날 동안(1) / 일주일 이상(2) / 거의 매일(3)
> 1. 일을 하는 것에 대한 흥미나 재미가 거의 없음 [0 1 2 3]
> 2. 가라앉은 느낌, 우울감 혹은 절망감 [0 1 2 3]
> 3. 잠들기 어렵거나 자꾸 깨어남, 혹은 너무 많이 잠 [0 1 2 3]
> 4. 피곤함, 기력이 저하됨 [0 1 2 3]
> 5. 식욕 저하 혹은 과식 [0 1 2 3]
> 6. 내 자신이 나쁜 사람이라는 느낌 혹은 내 자신을 실패자라고 느끼거나 나 때문에 나 자신이나 내
>    가족이 불행하게 되었다는 느낌 [0 1 2 3]
> 7. 신문을 읽거나 TV를 볼 때 집중하기 어려움 [0 1 2 3]
> 8. 남들이 알아챌 정도로 거동이나 말이 느림, 또는 반대로 너무 초조하고 안절부절 못해서 평소보다
>    많이 돌아다니고 서성거림 [0 1 2 3]
> 9. 나는 차라리 죽는 것이 낫겠다는 등의 생각 혹은 어떤 식으로든 스스로를 자해하는 생각들 [0 1 2 3]
> 점 수 / 27

**Fidelity check (2026-07-13 re-fetch):** all 9 items and the anchor set are byte-identical to
§1.2's alternate table and §1.3's government-form anchor quote — no item-text corrections
required. Item 8 (government variant) is confirmed exact: *"남들이 알아챌 정도로 거동이나 말이
느림, 또는 반대로 너무 초조하고 안절부절 못해서 평소보다 많이 돌아다니고 서성거림."* **Correction
found:** this document contains no Pfizer-style license/copyright footer anywhere on its single
page — see §1.5's corrected license note; the previous claim that "both" Korean PHQ-9 texts
carried this footer was inaccurate for this source.

### §A4 — Kim, Shin, Lee, Han (2021), Korean PHQ-4 standardization **[summary basis only]**

Kim HW, Shin C, Lee SH, Han C. "Standardization of the Korean Version of the Patient Health
Questionnaire-4 (PHQ-4)." *Clin Psychopharmacol Neurosci* 2021;19(1):104-111.
doi:10.9758/cpn.2021.19.1.104.

Quoted from the fetch-tool summary of `pmc.ncbi.nlm.nih.gov/articles/PMC7851451/` (≤15-word
fragments, per this project's quoting discipline): the Korean PHQ-4 "consists of the first two
items of the Korean version of the PHQ-9 ... and the first two items of the Korean version of the
GAD-7"; "All items are scored from 0 to 3 depending on the frequency ... over the preceding two
weeks"; sample "116 new adult psychiatric outpatients," mean PHQ-4 "6.52 (SD 3.45)," "PHQ-4 scores
of 6 (percentile 95.7%) or greater" as a flag threshold.

**Item-text traceability (2026-07-13 appendix-completion pass):** none of the 4 Korean PHQ-4 item
strings has an independent source — each is byte-identical to an already re-verified
parent-instrument row. PHQ-4 items 1-2 (anxiety subscale, §3.2) = GAD-7 items 1-2, quoted in full
at §A2 above. PHQ-4 items 3-4 (depression subscale, §3.2) = PHQ-9 items 1-2, quoted in full at §A1
above. A reviewer can verify all 4 PHQ-4 rows in §3.2 by cross-checking against those two appendix
blocks directly; only the *composition rule itself* (which two items, in which order) rests on
this paper's summary-basis citation.

### §A5 — SBIRT Oregon Korean AUDIT (full 10-item; items 1-3 = AUDIT-C) **[full PDF read]**

Retrieved 2026-07-13: `http://www.sbirtoregon.org/wp-content/uploads/AUDIT-Korean-pdf.pdf`

> 알코올 선별 설문조사 (AUDIT – Korean)
> 알코올 섭취는 귀하의 건강과 복용하는 일부 약에 영향을 미칠 수 있습니다. 귀하께 최선의 치료를
> 제공할 수 있도록 아래의 질문에 답해 주십시오.
> 1 잔의 기준: 12 온스(355mL) 맥주 / 5 온스(148mL) 와인 / 1.5 온스(44mL) 독주 (1 잔)
> 1. 알코올 음료를 얼마나 자주 마십니까? 마시지 않음 / 월 1회 또는 미만 / 월 2~4회 / 주 2~3회 / 주
>    4회 이상
> 2. 술을 마실 때 보통 알코올 음료를 몇 잔 정도 마십니까? 0~2잔 / 3~4잔 / 5~6잔 / 7~9잔 / 10잔 이상
> 3. 한 번에 4 잔 이상을 얼마나 자주 마십니까? 없음 / 월 1회 미만 / 월 1회 / 주 1회 / 매일 또는 거의
>    매일
> Citations: ... Thomas F. Babor, John C. Higgins-Biddle, John B. Saunders, Maristela G. Monteiro.
> The Alcohol Use Disorders Identification Test Guidelines for Use in Primary Care. 2nd Edition.
> World Health Organization. 2001.

### §A6 — Seong et al. (2009), Korean AUDIT-C validity study **[full PDF read]**

Seong JH, Lee CH, Do HJ, Oh SW, Lym YL, Choi JK, Joh HK, Kweon KJ, Cho DY. "일차진료에서 문제음주자
선별을 위한 Alcohol Use Disorders Identification Test Alcohol Consumption Questions (AUDIT-C)의
타당도 조사." *Korean J Fam Med* 2009;30:695-702. doi:10.4082/kjfm.2009.30.9.695.

> Background: ... we evaluated AUDIT-C, which covers questions from 1 to 3 in AUDIT-K ...
> Results: For AUDIT-C, we designated the score 8 or more as problem drinking, 9 or more as alcohol
> use disorder, and 11 or more as dependence. ... 82%/76%, 76%/79%, 80%/86%, respectively.
> 국내에서는 1998년 Kim 등이 AUDIT를 한국어로 번역하여 남성을 대상으로 AUDIT-K에 대한 타당도
> 조사를 실시한 바가 있으며 이에 12점 이상을 문제음주, 15점 이상을 알코올사용장애, 26점 이상을
> 알코올의존의 선별점수로 제안하였다.
> 이에 미국은 남자의 경우, AUDIT-C 총점 4점 이상을(민감도와 특이도 각각 86%, 72%), 여자의 경우, 2점
> 이상을(민감도, 특이도 각각 92%, 78%) 문제음주 선별점수로 제시하였으며 스페인은 남자의 경우, 5점
> 이상 ..., 여자의 경우, 4점 이상 ... 을 문제음주 선별점수로 제시하였다.
> 1, 2번 문항의 응답점수는 '전혀 안 마신다'가 0점, '일주일에 4번 이상'이 4점으로 계산되고 3번
> 문항의 응답점수는 '전혀 없다'가 0점, '거의 매일'이 4점으로 계산되어 AUDIT-C 총점은 최대 12점 ...

### §A7 — Kim et al. (1999), original Korean AUDIT-K validation **[full PDF read]**

Kim JS, Oh MK, Park BK, Lee MK, Kim GJ, Oh JK. "한국에서 Alcohol use disorders identification
test(AUDIT)를 통한 알코올리즘의 선별 기준" ("Screening criteria of alcoholism by alcohol use
disorders identification test (AUDIT) in Korea"). *J Korean Acad Fam Med* 1999;20:1152-1159.

> Conclusions: The authors recommend AUDIT cut-off scores of 12 points as the standard value for a
> broader sense of 'problem drinking' including physical as well as psychosocial problems, 15 for
> 'alcohol use disorders' based on DSM-IV criteria, and 26 for 'alcohol dependence' in Korea.
> Method: The subjects were 85 drinking men and 11 male alcohol dependents who visited Kangnung
> hospital ... during 1998.

(No Korean item-text appendix was present in the pages I could access — this paper is cited for
its Korean-population cutoff findings, not as an item-text source.)

### §A8 — Ahn, Kim, Choi (2019), Korean GAD-7/GAD-2 validation **[summary basis only]**

Ahn JK, Kim Y, Choi KH. "The psychometric properties and clinical utility of the Korean version of
GAD-7 and GAD-2." *Frontiers in Psychiatry* 2019;10:127. doi:10.3389/fpsyt.2019.00127.

Quoted from fetch-tool summary of `pmc.ncbi.nlm.nih.gov/articles/PMC6431620/`: "The Korean version
of the GAD-7 ... was used in the present study," described as "available on the Patient Health
Questionnaire website"; N=1,157; "GAD-7 ≥8" for GAD (sens 0.81/spec 0.85).

### §A9 — Moon, Kim, Kim (2014), Korean WHO-5 validation **[summary basis only, full text 403]**

Moon YS, Kim HJ, Kim DH. "The relationship of the Korean version of the WHO Five Well-Being Index
with depressive symptoms and quality of life in the community-dwelling elderly." *Asian J
Psychiatry* 2014;9:26-30. doi:10.1016/j.ajp.2013.12.014.

Quoted from search-result summary only (PubMed/ScienceDirect abstract-level, full text blocked by
403 both attempts): "A total WHO-5 score<13 indicated low well-being"; N=244 community-dwelling
elderly, Gangwon Province. **Retry 2026-07-13:** PubMed's own article page was directly fetched this
session and confirms no PMC deposit and no free full-text link exists for this article ("Free
article" label on PubMed points only to paywalled Elsevier/ClinicalKey full-text). OpenAlex
(`api.openalex.org/works/doi:10.1016/j.ajp.2013.12.014`) and Semantic Scholar
(`api.semanticscholar.org/graph/v1/paper/DOI:...`) were queried directly for an OA PDF location:
both return no `openAccessPdf`/`best_oa_location` PDF URL, only the paywalled DOI landing page
itself (OpenAlex: license CC-BY-NC-ND, "hybrid" OA status with no actual PDF location).

### §A9b — Kim, Moon, Son, Lee, Noh, Kim (2010), Korean WHO-5 validation (original Korean-language
report) **[abstract directly fetched from 3 independent database mirrors, full text still gated]**

Kim HJ, Moon YS, Son BK, Lee SK, Noh HJ, Kim DH. "지역사회에 거주하고 있는 노인의 우울증과 삶의 질을
평가하는 도구로 한국판 WHO-5의 유용성." *노인정신의학* (J Korean Geriatric Psychiatry) 2010;14(2):
90-96.

Directly fetched 2026-07-13 from three independent bibliographic-database pages — KCI
(`kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART001514454`),
DBpia (`dbpia.co.kr/journal/articleDetail?nodeId=NODE10936840`), and RISS
(`riss.kr/search/detail/ssoSkipDetailView.do?...control_no=99eec1a7a79320f8ffe0bdc3ef48d419`) — each
displaying the same English-language abstract. Quoted verbatim, identical across all three:

> Background and Objectives：Recently the number of geriatric depressed people has been increasing
> tremendously ...
> The total score of WHO-5 below 13 indicates low well-being.
> Low well-being group (WHO-5 score<13) ...
> Conclusion：The Korean version of WHO-5 was very useful to evaluate both depressive symptoms and
> quality of life in the aged dwelling in community.

Full text (Korean item wording, methods, results tables) was **not** reached: KCI's own "KCI 원문
내려받기" (KCI full-text download) button leads to an institutional-credential wall despite RISS
displaying a "무료" (free) badge for this specific record; DBpia shows abstract only, paywalled
beyond that. A guessed alternate KCI "org view" URL
(`kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiOrgView.kci?...`) returned HTTP 404 — not a
working access path.

### §A10 — Woo, Jang, Choi, Lee (2017), Korean AUDIT-K/AUDIT-C sex-specific cutoffs **[summary basis only]**

Woo SM, Jang OJ, Choi HK, Lee YR. "위험음주자 선별을 위한 한국판 알코올사용장애 선별검사(AUDIT-K),
알코올 소비 점수(AUDIT-C), 3번 문항(AUDIT3)의 유용성과 최적 절단값." *J Korean Acad Addict
Psychiatry* 2017;21(2):62-67. doi:10.37122/kaap.2017.21.2.62.

Quoted from fetch-tool summary of a scholarly-portal page: "N=509 participants (265 men, 244
women)"; "AUDIT-C Optimal Cutoff Scores: Men: 7, Women: 6"; "AUDIT-C and AUDIT3 were available for
detecting of hazardous drinking" per NIAAA criteria.

---

## 7. Summary table (developer quick reference)

| Instrument | Items sourced | Appendix-quoted (2026-07-13) | Anchors/timeframe sourced | Scoring | License | Primary source |
|:--|:--|:--|:--|:--|:--|:--|
| PHQ-9 | 9/9 (+ 9/9 alternate) | 9/9 both variants, §A1/§A3 | yes (both texts) | CONFIRMED (5 bands + item-9 flag) | CONFIRMED (Pfizer text only — government-form footer claim retracted, §1.5) | Pfizer phqscreeners.com; alternate = KR government form |
| GAD-7 | 7/7 | 7/7 primary + 7/7 alternate cross-check, §A2/§A2b | yes | structure unchanged; band **sourcing** downgraded to international-convention-only — Korean-PDF scoring-table citation retracted, §2.4 | CONFIRMED (Pfizer, verbatim) | Pfizer phqscreeners.com |
| PHQ-4 | 4/4 (composed, each half verbatim-sourced) | 4/4 traceable via §A1/§A2 (parent items), §A4 | yes (inherited, unharmonized) | CONFIRMED (structure + flag point) | CONFIRMED (inherited) | Composed per Kim et al. 2021 from Pfizer PHQ-9+GAD-7 |
| WHO-5 | 0/5 — full gap, retried 2026-07-13, still open | n/a — out of scope this pass (ADR-033 decision 7) | 0/5 — full gap | partial (percentage formula CONFIRMED; raw≤13 boundary now a CONFIRMED off-by-one discrepancy, directly sourced, not just unverified) | UNVERIFIED (summary basis) | none found — item text needs a non-WebFetch access path (§4.6) |
| AUDIT-C | 3/3 | 3/3, §A5 (unchanged this pass) | yes | DISCREPANCY flagged (Korean data suggests cutoffs ~2x current; translation-identity to Korean-validated instrument unconfirmed) | UNVERIFIED (WHO, no explicit permission text found) | SBIRT Oregon Korean AUDIT |

**Total: 23/23 claimed-verbatim items now appendix-quoted and independently auditable (CVR-016
condition 4 closed this pass; WHO-5's separate 0/5 item-text gap is untouched, out of scope per
ADR-033 decision 7). Re-fetch found 0 item-text mismatches across all 23 items — including PHQ-9
item 8 in both variants — but surfaced 2 unrelated sourcing errors, corrected loudly rather than
silently: (1) §1.5's government-form license-footer overclaim, (2) §2.4/§A2b's now-unconfirmable
GAD-7 Korean-PDF scoring-table citation. See §6's changelog for the full account.**
