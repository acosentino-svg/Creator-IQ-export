# OCTOBER BRIEF — Results (updated Nov 2, 2026)

**Data source:** CreatorIQ campaign **2206666** (Wayfair Creators Boosting Partnership), full **Oct 1–31, 2026** (Eastern), synced Nov 2, 2026.  
**Eligible posts** = both **#WayfairCreator** and **#wayfairelevate** in caption (case-insensitive).  
**September baseline** for program stats: Sep 2026 eligible counts from prior scorecard (**661 posts / 166 creators**) — update if your September pull differs.

---

## TL;DR

October suggests it helped: more posts per creator, healthy brief readership, and content that matched what we asked for (seasonal themes and priority categories). The boosting workflow stayed smooth, with solid creator follow-through on selected videos. Paid performance learnings are feeding into the November brief and updated boost/pass guidance.

---

## OCTOBER BRIEF

Results from the October boosting content brief, a test to see whether giving boosting creators clearer guidance on what we are looking for would drive more eligible content and stronger creative for paid boost.

### Test overview

- Shared an October boosting brief (platform priorities, messaging themes, deliverables, and boost/pass guidance) with creators in the boosting program.
- **What was measured:**
  - Program-level posting volume and active creators (September vs October)
  - Brief engagement (page visits)
  - How posted content mapped to brief themes (caption keyword classification)
  - Boosting pipeline outcomes (videos selected, creator follow-through)
- October also had natural seasonality (fall, Halloween, early holiday). Treated September as a directional baseline, not a perfect control.

---

## Results

### General boosting program stats

| | September | October | Change |
|--|--:|--:|--|
| **Eligible posts** | 661 | **824** | **+163 (+25%)** |
| **Active creators** (posted ≥1 eligible piece) | 166 | **165** | **−1** |

**Posts per active creator:** ~**4.0** in September → ~**5.0** in October (**+25%**).

> **Correction vs prior draft:** MoM post growth is **+25%**, not +10%. The +10% figure came from a bad delta display (partial-month / formatted-metric bug). October volume uses the **full month** after CreatorIQ sync, not a partial October cut.

---

### Brief engagement

*(Unchanged — from brief analytics, not CreatorIQ posts API.)*

- **411** unique visitors  
- **626** total visits (~1.5 visits per visitor)

---

### Content vs brief themes (October eligible posts)

Creators tagged or categorized against brief messaging pillars. **Pillar counts can overlap** (one post can match fall and pre-holiday). Sub-rows under category-specific are subsets of row 4.

| Theme | Examples | Posts |
|--------|-----------|------:|
| **1. Fall / fall refresh** | fall, autumn, fall decor, cozy fall, fall refresh, etc. | **156** |
| **2. Halloween** | Halloween, spooky season, trick-or-treat, etc. | **51** |
| **3. Pre-holiday** | Thanksgiving, Christmas prep, gift guide, hosting, Way Days, etc. | **126** |
| **4. Category-specific** (any of below) | sideboards, pet, Wayfair Verified | **82** |
| ↳ Sideboards / consoles | sideboard, console, buffet, credenza | **54** |
| ↳ Pet | pet, dog, cat, pet bed | **19** |
| ↳ Wayfair Verified | Wayfair Verified, verified badge | **9** |
| **5. Single product highlights** | One hero piece, not full room hauls | **41** |

**367** eligible October posts matched **at least one** brief pillar (**45%** of 824 eligible posts).

> **Correction vs prior draft:** “410 posts mapped” overstated unique coverage (likely partial-month data or summing overlapping pillars). Use **367** unique posts with ≥1 theme, or cite individual pillar counts above knowing they overlap.

---

### Boosting selection (October)

*(Unchanged — confirm against your boosting ops / scorecard `selected` flags.)*

- **73** videos selected for boost  
- **61** with links (**84%** creator response rate among selected)  
- **47** unique creators represented in the boost pool  
- Overall creator boosting ACNR decreased from September to October  

---

## Key takeaways (edited)

- **Volume:** October posted **~25% more eligible posts** than September (**824 vs 661**), with higher output per creator (~**5.0 vs ~4.0** posts per active creator) while active creator count was **roughly flat (−1)**.
- **Brief adoption:** 411 unique visitors and 626 visits suggest creators are using the brief as a reference, not only at first publish.
- **Message pull-through:** Highest-volume themes (fall refresh, pre-holiday, Halloween) matched October brief priorities. Sideboards/consoles (**54 posts**) aligned with TikTok category emphasis in the brief.
- **Boosting ops:** 73 selections and 84% link completion among selected videos show the brief did not add friction to the boost workflow; creator follow-through stayed strong.

**Quality (early read):**

- Theme alignment and selection volume improved  
- Paid performance learnings (hero product, first 3 seconds, seasonal structure) are being folded into the November brief  
- Updated we boost / we pass guidance with Meta  

---

## NOVEMBER BRIEF

*(Continue from your existing November section.)*

---

## Regenerate these numbers

```bash
CREATORIQ_DASHBOARD_MODE=live python scripts/export_campaign_posts.py \
  --campaign-id 2206666 --start 2026-10-01 --end 2026-10-31 \
  --timezone America/New_York \
  -o data/boosting_campaign_2206666_posts_2026-10-full.csv

python scripts/classify_campaign_captions.py \
  data/boosting_campaign_2206666_posts_2026-10-full.csv --eligible-only \
  -o data/boosting_campaign_2206666_posts_2026-10-full_eligible_by_theme.csv

python scripts/october_brief_report_stats.py data/boosting_campaign_2206666_posts_2026-10-full.csv
```
