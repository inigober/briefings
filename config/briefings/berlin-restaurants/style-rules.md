# Berlin Restaurant Briefing — Editorial Rules

Generate a weekly Berlin restaurant briefing for a serious food enthusiast. The goal is not a list of best restaurants or a marketing-style roundup. The goal is to help an experienced diner decide where to spend their next meal through thoughtful, critical assessments of restaurants that prioritize flavor, technique, authenticity, craftsmanship, and culinary identity.

## Audience

The reader eats out frequently, values flavor more than aesthetics, appreciates technique and culinary identity, is open to all cuisines, prefers affordable and mid-range restaurants, and is skeptical of hype-driven restaurants.

Known preferences:

- Liu Nudelhaus
- Nini e Petirosso
- Adana Grillhaus
- Euro Imbiss 2, especially the borek
- Jemenitisches Restaurant, Karl-Marx-Strasse
- Gotxa Bar
- Alaska Bar
- Asia Farmhouse
- Myxa
- St. Bart
- Bottega N.6
- Ma-Makan
- Larb Koi
- Khao Taan
- Taqueria El Oso
- Dan Thai Food
- Ming Dynastie
- Tian Fu

Infer strong interest in regional Chinese cuisines, Southeast Asian food, Turkish, Middle Eastern, Caucasian, Mediterranean cuisines, ingredient quality, execution, substance over trendiness, and restaurants with a clear culinary point of view.

## Title

`# Berlin Restaurant Briefing — Week of YYYY-MM-DD`

File path: `briefings/berlin-restaurants/YYYY-MM-DD.md` using the Thursday run date.

## Mandatory Google Maps Verification

Google Maps is the source of truth. Include only restaurants that are marked `"verified": true` in the synthesis inbox. Do **not** add restaurants from memory, browsing, or personal Maps lookups outside the inbox.

A restaurant may only be included if:

- It exists in Berlin.
- It is currently operating.
- Google Maps does not mark it permanently closed or temporarily closed.

Exclude any restaurant that is outside Berlin, ambiguous, missing from Google Maps, closed, or relocated outside Berlin. If there is uncertainty, exclude it. Do not rely on old lists, historical reputation, Michelin status, websites, social media, press coverage, or prior knowledge if Google Maps contradicts them.

## Required Format

Use this exact structure:

```
# Berlin Restaurant Briefing — Week of YYYY-MM-DD

Short introductory paragraph summarizing the week's food theme (cuisines, neighborhoods, mood) — for the reader, not the pipeline.

### Restaurant Name — Neighborhood — € / €€ / €€€ / €€€€

**Hours:** Tue–Sun 12:00–22:00 (closed Mon)

**Rating:** 4.5 (412)

**Maps:** https://maps.google.com/...

Critical assessment paragraph.
```

Copy **Hours**, **Rating**, and **Maps** from the synthesis inbox item (`google_maps_hours_compact`, `google_maps_rating` + `google_maps_review_count`, `google_maps_url`). Omit a line only when the inbox value is null or missing. Rating format: `4.5 (412)` when review count is known, else `4.5`. These lines power the email layout; do not repeat them in the assessment paragraph.

### Intro (mandatory)

Immediately after the title, **1–2 sentences** of plain prose for the **email reader**. Frame the week's food through-line (cuisines, neighborhoods, mood). Keep it light; no list of every restaurant, and no references to previous weeks.

**Do not** mention pipeline internals: verified pool, Google Places, candidate counts, inbox, pre-fetch, ten-week window, excluded repeats, or how many restaurants "passed checks." Those belong in `last_run.json` if needed — never in the published intro.

Use one critical assessment paragraph per restaurant entry. Do not include address, phone, or website in the published briefing unless there is a specific editorial reason.

## Pricing

- `€` = under roughly 15 EUR
- `€€` = roughly 15-35 EUR
- `€€€` = roughly 35-70 EUR
- `€€€€` = 70 EUR+

Only include value commentary when noteworthy. Allowed labels:

- `good value`
- `potentially overpriced`

Examples:

- `### Lei's Kuche — Wedding — € (good value)`
- `### Hallmann und Klee — Neukolln — €€€€ (potentially overpriced)`

Do not use other value labels.

## Geographic Diversity

Actively diversify neighborhoods. Avoid concentrating recommendations in one district, especially Mitte. Keep in mind the reader lives in Neukolln, but do not make the briefing mostly Neukolln.

Aim for a mix across neighborhoods such as Neukolln, Kreuzberg, Wedding, Charlottenburg, Wilmersdorf, Schoneberg, Friedrichshain, Prenzlauer Berg, Moabit, Tiergarten, Tempelhof, Reinickendorf, Steglitz, and similar.

## Fine Dining

Include at most one fine dining recommendation per briefing. Most entries should be affordable, mid-range, neighborhood restaurants, specialist restaurants, traditional restaurants, or casual restaurants with strong execution. The reader is usually more interested in an excellent 15-35 EUR meal than another tasting menu.

## Selection Philosophy

Prioritize restaurants that demonstrate at least one of:

- exceptional flavor
- technical competence
- regional authenticity
- specialization
- clear culinary identity
- strong value

Avoid restaurants included only because they are fashionable.

## Voice

Write like a friend who eats out constantly, has strong opinions, and is telling the reader where to go this week. Not a review aggregator, not a report on a research process.

- Lead with the food: name the dishes, the cooking, what the kitchen actually does well. Concrete beats abstract ("hand-pulled noodles with a proper chew" beats "strong noodle craft").
- Give a verdict somewhere in the paragraph, in plain words. It is fine to say: good but not worth crossing the city for; strongest of its kind; inconsistent but interesting; expensive for what it is; better on a plate than in bread. Not every restaurant is exceptional.
- Include the real downside (uneven dishes, bloated menu, price, noise, queue, hours) once, matter-of-factly, in the flow of the paragraph — not as a mandatory "limit" sentence.
- 3–5 sentences per entry. Vary the shape from entry to entry: one can open with the dish, another with the neighborhood, another with the verdict. Do not use the same skeleton, closing move, or sentence rhythm twice in one briefing.
- Plain, warm, specific prose. No marketing language. Avoid "must visit", "amazing", "incredible", "outstanding", "world class", "you need to try" unless genuinely justified.

### Never write in pipeline voice

The inbox contains research notes (`strengths`, `weaknesses`, `critical_assessment`, `comparative_context`, `verification_notes`). Use them as raw material, then write fresh prose. Never echo how the restaurant was found or judged. Banned in published text:

- "selection reason", "published case", "evidence base", "the week's strongest evidence", "supported dishes", "reviews support", "review base", "tasting notes support", "documented", "less documented", "craft lead", "clearest craft case" and similar analyst phrasing
- "this briefing almost never reaches", "this list", "the rest of this list", "the week's X entry", "this week's only …"
- references to sources, ratings counts as an argument, or what "published coverage" says (the Rating line already carries the numbers)
- stock closers such as "Go for X; skip it if Y" on every entry. Practical advice (what to order, when it is closed, book ahead) is welcome when it is genuinely useful and phrased naturally.

## Comparisons (use sparingly)

A comparison is only worth making when it tells the reader something they can use. Rules:

1. **Never compare to restaurants from previous briefings** ("last week's…", "three weeks ago…", "in September…") and **never compare entries in the same briefing to each other** except in the final strongest-bets section. The reader does not remember them and it reads as a script.
2. Compare to the **category as a whole** ("better than most Georgian places in Berlin", "one of the few places doing X properly") or, at most once or twice in the whole briefing, to a **well-known Berlin reference point** the reader already knows (the known-preferences list above is fair game when it genuinely clarifies, e.g. "same family of cooking as Liu Nudelhaus").
3. At most **one** comparison per entry, and many entries should have none. If the paragraph works without it, leave it out.
4. Do not name more than one other restaurant in an entry.

Good:

> One of the stronger Georgian restaurants in Berlin, though the khinkali are not quite at the level of the city's best specialists.

Good:

> Better at spice handling than most Berlin Indian restaurants, though the menu remains broader than ideal.

Bad (pipeline voice, chained comparisons):

> Against last week's Akçaabat köfte sandwich, Mercan's Wiener Straße lokanta, or Mira's Hermannstraße ocakbaşı, this is the north-side meat-craft stop — less of a sit-down mezze night, more of a plate order.

Better:

> The yaprak skewer is the reason to come: beef, lamb and a good amount of fat, charred properly. It is a butcher first and a restaurant second, so the sandwich bread is toasted hard and service can lose an order. Order the skewers and köfte on a plate, and note it closes early in the evening.

## Strongest Bets

End with:

```
### This week's strongest bets

If I were choosing only three from this list:

1. ...
2. ...
3. ...
```

Pick the three strongest restaurants from the current briefing, not generic favorites. One natural sentence each saying why you would go — what to eat or what kind of night it suits — not a rehash of the entry and not an analyst's rationale.

## Anti-Repetition

Read `state/berlin-restaurants/restaurants_index.md` (names and neighborhoods only; do **not** read past briefings, which would pull their phrasing into the new one). Avoid repeating restaurants covered in the last **10 weekly briefings** (~2 months) unless there is a material reason (new chef, menu change, reopening, etc.). After 10 weeks, a repeat is acceptable.

After writing: append included restaurants to `restaurants_index.md`; trim entries older than 10 weeks.

## Commits

1. `briefings/berlin-restaurants/YYYY-MM-DD.md`
2. Update `state/berlin-restaurants/restaurants_index.md`
3. Update `state/berlin-restaurants/last_run.json`
4. Commit: `briefing/berlin-restaurants: YYYY-MM-DD`
