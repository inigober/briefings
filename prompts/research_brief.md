# Research Brief — OpenAI Pre-fetch Prompt

Gather raw research for a personal daily briefing. Today is **{date}**.

## Important: inbox is a warehouse, not the briefing

Cast a **wide net**. The synthesis step will select only ~3 stories per section and apply deduplication. Your job is to **over-collect** so the editor always has alternatives after novelty filters remove repeats.

**Target volume (minimums):**

| Section | Minimum items | Notes |
|---------|---------------|-------|
| Spain 🇪🇸 | **15** | Economy, demographics, infrastructure, energy, water, rail, regions, science |
| Germany 🇩🇪 | **15** | Labour, industry, demographics, energy, transport, healthcare, coalition |
| Berlin 🏙️ | **12** | Local only — transport, planning, universities, health, culture, policing |
| World 🌐 | **25** | **At least 5 per non-European region** (Americas, Asia, Africa, Middle East) |
| Selected Reads 🗞️ | **15** | Long-form, think-tank, specialist, news analysis — diversified |

**Total: 60–80+ news items** plus 15 read candidates. More is better if quality holds.

## Reader profile

Interested in Spain, Germany, Berlin, international affairs, economics, urbanism, infrastructure, technology, demography, culture, and long-term structural trends. Values novelty, insight, and underreported developments over headline churn.

## Task

Run **multiple searches** by section and region. Prioritize:

- Material developments (legislation, rulings, data releases, policy changes) over commentary
- Structural and long-term trends, second-order effects, underreported stories
- Primary reporting from allowed domains
- **World: mandatory non-European coverage** — search explicitly for India, China, Brazil, Mexico, Nigeria, Indonesia, Japan, South Korea, US, South Africa
- Berlin-local stories (not generic Germany)

Do **not** optimize for "biggest headlines today." Include near-duplicate angles on hot topics — synthesis will dedupe.

## Sections to research

{topics_summary}

## Allowed domains

Prefer results from:

{allowed_domains}

## World section — explicit search queries required

Before finishing, confirm you have sourced stories from **at least 4 non-European countries** across **at least 3 regions**. If initial searches are Europe-heavy, run additional searches:

- "India" + industrial policy / demographics / technology
- "China" + semiconductors / energy / trade
- "Brazil" or "Mexico" + economy / infrastructure
- "Nigeria" or "South Africa" + energy / demographics
- "Japan" or "South Korea" + technology / labour

## Output format

Return **valid JSON only** (no markdown fences):

```json
{
  "date": "YYYY-MM-DD",
  "fetched_at": "ISO-8601",
  "items": [
    {
      "id": "slug",
      "topic_ids": ["spain"],
      "headline": "...",
      "summary": "...",
      "why_it_matters": "...",
      "broader_context": "...",
      "region": "Spain | Germany | Berlin | North America | East Asia | ...",
      "country": "Spain",
      "is_structural": true,
      "is_follow_up": false,
      "material_development": true,
      "sources": [{"title": "...", "url": "https://...", "publisher": "...", "published_at": null}]
    }
  ],
  "selected_read_candidates": [
    {
      "title": "...",
      "url": "https://...",
      "publisher": "...",
      "type": "long_form_feature | think_tank_research | specialist_publication | news_analysis",
      "summary": "..."
    }
  ],
  "gaps": ["only list genuine thin areas after meeting minimums"],
  "search_notes": "paywall limits, regions searched, query count"
}
```

## Quality rules

- Every item needs at least one **article-level URL** (not a homepage)
- Include items even if thematically similar — synthesis handles novelty
- `selected_read_candidates` must include URLs **not** duplicated as news items where possible
- Report `items.length` by topic_id in `search_notes`
