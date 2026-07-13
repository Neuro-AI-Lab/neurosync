# WHO-5 sourcing — second, deeper retry attempt

> **Mission:** second dispatch (orchestrator-directed) to source the official Korean WHO-5
> Well-Being Index item text, anchors, instruction, and scoring-boundary sentence, following the
> first two dispatches logged in `docs/ai/item_bank_v1_sources.md` §4 (both under `PLAN-2026-W29-A`).
> **Author:** brainstorm | **Date:** 2026-07-13
> **Fabrication discipline (unchanged):** every Korean-language string below is either
> `verbatim-from-source` with a fetchable citation, or absent. No paraphrase, no back-translation,
> no reconstruction from memory or from the English instrument. This file does not modify
> `item_bank_v1_sources.md` — that serialization is a later, separate pass per the brief.
> **Result up front:** still **0/5 items, 0/5 anchors, no instruction/timeframe text** found in
> Korean. The scoring-boundary sentence (English, from the primary Korean study's own abstract) is
> now independently confirmed across a 4th mirror. One new authoritative negative finding narrows
> the gap's cause: WHO's own current (2024, post-copyright-transfer) official translation list does
> not include Korean among its ~26 completed languages — see §2.1.

---

## 1. Retry log — every source attempted this session

Legend: **F** = fetched successfully (content read), **T** = timeout, **404** = not found, **403**
= forbidden/blocked, **∅** = searched, no relevant result, **RETIRED** = confirmed dead end on a
second+ independent attempt.

### 1.1 Priority target (a) — official WHO-5 host (who-5.org / psykiatri-regionh.dk) + archive mirrors

| # | Source / URL | Method | Outcome |
|:--|:--|:--|:--|
| 1 | `who-5.org` — broad web search for a Korean-hosted PDF at this domain | WebSearch | ∅ — no who-5.org-hosted Korean file surfaced; this domain does not appear to independently host translation PDFs (it points to the same Region H collection) |
| 2 | `psykiatri-regionh.dk/who-5/who-5-questionnaires/Pages/default.aspx` (the questionnaire-collection index page) | WebFetch | **T** — timeout (60s). This exact page was not tried in either prior dispatch; new URL, still fails |
| 3 | `psykiatri-regionh.dk/who-5/references/Pages/default.aspx` | WebFetch | **T** — timeout (retry of a page a prior dispatch also timed out on; 2nd failure on this specific URL) |
| 4 | `web.archive.org/web/2023/https://www.psykiatri-regionh.dk/who-5/who-5-questionnaires/Pages/default.aspx` | WebFetch | **403/blocked** — "Claude Code is unable to fetch from web.archive.org." Retried once per the brief's instruction (transient-timeout hypothesis); result unchanged from the prior dispatch. **RETIRED** — this is a categorical tool-level block, not a transient failure; do not retry a 3rd time in a future session without a different fetch mechanism |

**Running tally for `psykiatri-regionh.dk`:** 5 timeouts (2 dispatches, prior sessions) + 2 timeouts
(this session, 2 new URLs) = **7 attempts, 7 failures, 0 successes**, across 3 sessions and 5
distinct URL paths (bare root, References page ×2 attempts, Korean-PDF direct guess, Questionnaires
page). This is now a very well-established environment-level dead end for this specific host, not a
fluke of any one URL.

### 1.2 Priority target (b) — WHO document repositories

| # | Source / URL | Method | Outcome |
|:--|:--|:--|:--|
| 5 | `who.int/publications/m/item/WHO-UCN-MSD-MHE-2024.01` — WHO's own 2024 official WHO-5 publication page (post copyright-transfer from Psychiatric Centre North Zealand) | WebFetch | **F — key finding.** This page lists WHO's current, complete set of official translation-PDF links. It names **26 languages** (Albanian, Bangla, Bulgarian, Chinese PR, Czech, Danish, Dutch, Farsi, Filipino, Finnish, German, Greek, Hebrew, Hungarian, Icelandic, Italian, Japanese, Lithuanian, Norwegian, Polish, Romanian, Slovenian, Swedish, Thai, Turkish, Urdu) at the URL pattern `cdn.who.int/media/docs/default-source/mental-health/five-well-being-index-(who-5)/who-5_<language>.pdf`. **Korean is not among them.** This is stronger and more specific than the prior dispatch's finding (which only showed a Korean 404 on a URL guess) — this is WHO's own current canonical list, fetched directly, confirming the absence is not a fetch-tool artifact but reflects WHO's actual publication state as of this note |
| 6 | `cdn.who.int/media/docs/default-source/mental-health/five-well-being-index-(who-5)/who-5_korean.pdf` (direct guess, consistent with the pattern found in #5) | WebFetch | **404** — confirms #5; no Korean file exists at the pattern used for all 26 other languages |
| 7 | WPRO (WHO Western Pacific Regional Office) — any regionally-published Korean translation independent of the global cdn.who.int list | WebSearch | ∅ — no WPRO-specific Korean WHO-5 translation found; only the general systematic-review literature noting WHO-5 has been *used* in South Korea (not that WPRO published a translation) |

### 1.3 Priority target (c) — Korean validation papers' appendices (Kim et al. 2010, Moon et al. 2014) + open-access mirrors, KoreaMed, RISS, KCI

| # | Source / URL | Method | Outcome |
|:--|:--|:--|:--|
| 8 | KCI article page, `ART001514454` (Kim et al. 2010) — re-fetched | WebFetch | **F** — same English abstract as the prior dispatch (title, keywords, no download link); no new content, no item text |
| 9 | `m.riss.kr/search/detail/DetailView.do?...control_no=99eec1a7a79320f8ffe0bdc3ef48d419` (RISS **mobile** detail page — not tried in either prior dispatch) | WebFetch | **F** — full English abstract fetched directly, including the verbatim sentence *"The total score of WHO-5 below 13 indicates low well-being."* This is a **4th independent mirror** of that sentence (after KCI, DBpia, RISS-desktop in the prior dispatch), and the first one fetched from the *mobile* RISS interface — confirms the desktop-vs-mobile RISS pages carry identical text, not a caching artifact. No full-text/PDF download link present on this page either ("구독기관에 따라 유료논문이 존재할 수 있습니다") |
| 10 | 대한노인정신의학회 (Korean Association for Geriatric Psychiatry) official site, `kagp.or.kr` | WebFetch | **F** — homepage fetched; surfaced a "학회지 검색" (journal search) link to a *separate* subdomain, `journal.kagp.or.kr` — a genuinely new lead not tried in either prior dispatch |
| 11 | `journal.kagp.or.kr` (bare root) | WebFetch | **403 Forbidden** |
| 12 | `journal.kagp.or.kr/custom/212/pdfFile/journal.pdf` — a confirmed-indexed direct-PDF URL pattern for this host (found via search, belongs to a *different* 2010 article, not the WHO-5 one — used here only to test whether the pattern is fetchable at all) | WebFetch | **403 Forbidden**, retried once (2 attempts total) — **RETIRED**. This confirms the block is host-level (any article on `journal.kagp.or.kr`), not specific to a missing WHO-5 article ID. This is a new, now-documented dead end alongside `psykiatri-regionh.dk` and `ncmh.go.kr` |
| 13 | `synapse.koreamed.org` — searched for the Kim et al. 2010 paper or any KoreaMed-hosted mirror | WebSearch | ∅ — 노인정신의학 (Journal of Korean Geriatric Psychiatry) does not appear to be a KoreaMed/KAMJE-indexed journal (searches surfaced only unrelated papers that *cite* it, never a KoreaMed page *for* it) |
| 14 | `koreascience.kr` (KISTI's open-access Korean STEM-journal platform) — publisher page `koreascience.kr/publisher/kagp.page?lang=ko`, direct search endpoint, and JAKO-code guesses | WebFetch + WebSearch (5 attempts) | ∅ / **400 Bad Request** on the search endpoint. No JAKO code for this specific article was found despite an extensive search; 노인정신의학 does not appear to be indexed on KoreaScience the way `kjfm.or.kr`/`headache.or.kr` self-host their own journals (those worked in the first dispatch; this journal's platform does not have the same open pattern) |
| 15 | NDSL / ScienceON (KISTI's national science library, successor portal) — `ndsl.kr` journal-detail page and `scienceon.kisti.re.kr` article search | WebFetch + WebSearch | **F** (redirect resolved successfully to scienceon.kisti.re.kr) but landed on a generic "AI-Reviewer" interface with no article metadata; the journal-level `cn=NJOU00291879` code found is not the article-level `cn=JAKO...` code needed, and no article-level JAKO code for this specific 2010 paper was located |
| 16 | Moon et al. 2014 (*Asian J Psychiatry*, English-language sibling paper) — re-checked via OpenAlex's own structured API (`api.openalex.org/works/doi:10.1016/j.ajp.2013.12.014`) | WebFetch | **F — clarifying finding.** OpenAlex's `best_oa_location` reports `is_oa: true`, license `cc-by-nc-nd`, but **`pdf_url: null`** — the only location is the paywalled Elsevier DOI landing page itself, plus a PubMed record with no PMC deposit. This clarifies (vs. the prior dispatch's "403, blocked") that there is **no PDF location anywhere in OpenAlex's index to even attempt** — the "open access" flag here is a formal/hybrid-OA metadata label, not an actually-reachable free PDF |
| 17 | KoreaMed indexing status check for 노인정신의학 generally | WebSearch | ∅ — inconclusive; no KoreaMed journal-profile page for this title was found, consistent with #13 |

### 1.4 Priority target (d) — Korean university repository PDFs (RISS 학위논문, institutional repositories)

| # | Source / URL | Method | Outcome |
|:--|:--|:--|:--|
| 18 | RISS 학위논문 (theses) search for "WHO-5 안녕감 지수 한국판" | WebSearch | ∅ — no thesis reproducing WHO-5 Korean item text found |
| 19 | dCollection (multi-university digital repository network: Korea Univ., Sejong, Sogang, Gachon, etc.) search for "WHO-5" + 안녕/지수/척도/원문 | WebSearch | ∅ — no matching thesis found; results were dCollection's own how-to-submit pages, not content |
| 20 | 국회전자도서관 (`dl.nanet.go.kr`, National Assembly Library) — search endpoint direct guess | WebFetch + WebSearch | **F** (page loaded) but returned "요청하신 페이지를 찾을 수 없습니다" (page not found) for the guessed query URL; no working search path found without a browser-rendered session |
| 21 | Korean-language graduate-thesis/workplace-wellbeing search (candidate contexts: employee stress surveys, workplace wellbeing indices) | WebSearch | ∅ — no thesis appendix reproducing the item text found |

### 1.5 Other avenues tried (not in the brief's priority list, opportunistic)

| # | Source / URL | Method | Outcome |
|:--|:--|:--|:--|
| 22 | Broad Korean-phrase candidate search — testing whether *any* already-published Korean paper/self-test site uses common back-translation phrasings for WHO-5 items (e.g. "명랑하고 기분이 좋았다", "차분하고 편안하게", "활기차고") — **searched for, never composed or used as content** | WebSearch | ∅ — no document surfaced reproducing these or any other candidate item phrasing |
| 23 | Korean workplace/public-health mental-health screening kit appendices (근로복지공단, 안전보건공단, 국민건강보험공단) | WebSearch | ∅ — no publicly surfaced appendix containing WHO-5 Korean items |
| 24 | Semantic Scholar API, direct query for Korean WHO-5 papers | WebFetch | **429 Too Many Requests** — consistent with the known no-API-key shared rate pool (see agent memory); not retried a 2nd time this session, OpenAlex used instead where duplicate coverage existed |
| 25 | OpenAlex API, broad + title-restricted searches for "WHO-5 Korean well-being index" | WebFetch (×2) | ∅ — 0 directly relevant new results beyond the already-known Kim 2010 / Moon 2014 records (confirmed again: Kim 2010 has no OA location in OpenAlex's index either) |
| 26 | WHO-5's own project on `localize.drupal.org` (the who5.org website's software-translation project) — has a listed Korean `.po` translation file | WebFetch → follow-up WebFetch on `ftp.drupal.org/files/translations/6.x/who5/who5-6.x-1.0-beta1.ko.po` | **F, checked and ruled out.** The Korean `.po` file (525 bytes, dated 2011) contains exactly **2** translated strings — UI labels for the *website software* ("Submit"→"전송", "Summary"→"요약") — **no instrument item text of any kind.** This is a genuinely new lead, investigated to completion, and definitively not a source of item text (documented so a future session does not re-open it) |

**Note on WebSearch-tool self-generated inferences:** one search response (row-adjacent to #17 in
the raw session, not tabled above) speculatively asserted a JAKO code "corresponds to" this paper
without evidence — that claim is explicitly **not** adopted here; no JAKO code for the target
article was actually confirmed.

---

## 2. Findings

### 2.1 New: WHO's own current translation list does not include Korean

Directly fetched from `who.int/publications/m/item/WHO-UCN-MSD-MHE-2024.01` (WHO's own official
item page, published after WHO accepted copyright of the WHO-5 from the Psychiatric Centre North
Zealand in 2024): the current list of **26** completed-and-published translations does **not**
include Korean. Combined with the confirmed 404 on the Korean URL at the same naming pattern used
for all 26 other languages, this is the most authoritative negative evidence obtained across all
three sourcing sessions — it indicates WHO itself has not yet published an official Korean WHO-5
translation, rather than merely that this project's tooling cannot reach one that exists.

### 2.2 Scoring-boundary sentence — now confirmed across a 4th independent mirror

Kim HJ, Moon YS, Son BK, Lee SK, Noh HJ, Kim DH (2010). "지역사회에 거주하고 있는 노인의 우울증과
삶의 질을 평가하는 도구로 한국판 WHO-5의 유용성." *노인정신의학* (J Korean Geriatric Psychiatry)
14(2):90-96.

Quoted verbatim, directly fetched this session from `m.riss.kr`'s mobile detail page (a 4th
independent mirror, joining KCI/DBpia/RISS-desktop from the prior dispatch):

> The total score of WHO-5 below 13 indicates low well-being.

This is an **English-language sentence from the Korean paper's own English abstract** — it is not
Korean-language text, and it is a **raw-score** rule (13 falls in the 0-25 raw range; the paper's
abstract does not state a percentage-score, i.e. ×4/0-100, cutoff anywhere in the text fetched).
The general WHO-5 percentage-score transform (raw×4 = 0-100 scale) is the instrument's universal
international convention, confirmed by every general WHO-5 source touched across all three
sessions, but that transform is not itself sourced to this Korean-population paper — it is a
structural property of the instrument, reported separately in `item_bank_v1_sources.md` §4.4.
**This finding does not change `item_bank_v1_sources.md`'s existing off-by-one discrepancy
finding** (implementation `raw<=13` vs. source "below 13" = raw<13); it only strengthens the
evidence tier of that finding from "3 mirrors" to "4 mirrors, including one fetched from a
previously-untried access path (mobile RISS)."

### 2.3 Item text, anchors, instruction/timeframe — still absent

No Korean-language WHO-5 item, response anchor, or instruction/timeframe text was found anywhere
this session. Every priority avenue in the brief was tried, several to a confirmed dead end
(`psykiatri-regionh.dk` now 7/7 failed attempts across 3 sessions; `journal.kagp.or.kr` newly
confirmed 403-blocked on 2 attempts; `web.archive.org` reconfirmed categorically blocked).

---

## 3. Gap statement (explicit, per fabrication-0)

**The gap stands. No Korean-language WHO-5 item text, response anchor text, or
instruction/timeframe text is included anywhere in this note or `item_bank_v1_sources.md`.**
Nothing here is paraphrased, back-translated from the English instrument, or reconstructed from
memory. All 5 items remain fully absent, exactly as `item_bank_v1_sources.md` §4.2/§4.6 already
state, per `ADR-033` decision 7 (WHO-5 stays unpopulated in v1).

What changed this session is the **evidence quality around the gap itself**, not the gap:
- The absence is now traceable to WHO's own current publication state (§2.1), not only to this
  project's fetch-tool limitations — a materially stronger claim than "we could not reach it."
- Every access path realistically available to this tooling environment for priority targets (a)
  through (d) has now been tried, several on a second independent attempt as the brief instructed,
  with two more hosts (`journal.kagp.or.kr`, the Drupal l10n project) newly ruled out rather than
  left unexplored.
- The scoring-boundary evidence is now on its 4th independent mirror (§2.2).

**Recommended next step, unchanged in substance from the prior dispatch's recommendation:** this is
not a "retry with the same tooling a 3rd time" gap. The remaining realistic paths are (a) asking the
user directly whether they hold institutional KCI/DBpia/RISS credential access or a cached copy of
Kim et al. 2010's full text or the WHO-5 Korean PDF from prior clinical/research use — this is now
the single highest-value unblock per `discussion.md`'s own open-questions list — or (b) a future
session with a fetch mechanism not subject to this environment's `psykiatri-regionh.dk`/
`journal.kagp.or.kr`/`web.archive.org` blocks.

---

## 4. Naming caution (reaffirmed)

Per the brief and per `CVR-016` Finding 11 / `item_bank_v1_sources.md` §4.1: **do not label the
WHO-5 "안녕지수" in Korean.** That term is in active, well-established use for a different,
unrelated instrument (Seoul National University Happiness Research Center / Kakao's real-time
happiness-tracking survey). Nothing in this session's searches changed that assessment — if
anything, this session's broad Korean-language searches (§1.5 row 22) reconfirmed that "안녕지수"
and "안녕감척도" search terms overwhelmingly surface the SNU/Kakao instrument or generic WHO
background pages, not the WHO-5.
