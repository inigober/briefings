# Research Brief — OpenAI Pre-fetch Prompt

Gather raw research for a personal daily briefing. Today is **{date}**.

## Reader profile

Interested in Spain, Germany, Berlin, international affairs, economics, urbanism, infrastructure, technology, demography, culture, and long-term structural trends. Values novelty, insight, and underreported developments over headline churn.

## Task

Search the web and compile candidate material for synthesis. Prioritize:

- Material developments (legislation, rulings, data releases, policy changes) over commentary
- Structural and long-term trends, second-order effects, underreported stories
- Primary reporting from allowed domains
- Geographic diversity for World (not Europe-only)
- Berlin-local stories (not generic Germany)

Do **not** optimize for "biggest headlines today."

## Sections to research

{topics_summary}

## Allowed domains

Prefer results from:

{allowed_domains}

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
      "region": "Spain | Germany | Berlin | North America | ...",
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
  "gaps": ["thin coverage areas"],
  "search_notes": "paywall limits, etc."
}
```

## Volume

- **25–40** news candidates across Spain, Germany, Berlin, World (synthesis will dedupe to 3 each)
- **8–12** Selected Read candidates meeting source-mix diversity
- Flag `avoid_unless_material` topics from config only when genuinely material
