# Design research (what was actually viewed)

Browsed with a real browser on 2026-11-26; screenshots are in the working session only. Logged-in product screens (ChatGPT,
Gemini, Claude, Linear, Notion, Intercom, Stripe dashboard) were **not** accessible, so observations come from their public
pages and docs, not from using them.

| # | Reference | Seen | Pattern taken |
|---|---|---|---|
| 1 | Dribbble "AI Chat Assistant SaaS Dashboard" | shot page | centred greeting + one question + composer; slim left rail |
| 2 | Dribbble "Knowledge Source" | shot page | upload as a chooser of source types with progress; mapped to "A company document / A step-by-step procedure" |
| 3 | Dribbble search: ai-assistant-interface | loaded (limited) | restraint: few controls around the composer |
| 4 | Dribbble search: assistant-dashboard | loaded | compact KPI row then lists, not big cards |
| 5 | Dribbble search: chat-ui-dashboard | loaded | list-and-detail for conversations |
| 6 | 21st.dev AI-chat components | browsed | suggestion chips, whitespace, quiet buttons |
| 7 | Gemini (public app page) | screenshot | one rounded composer with the microphone inside it; calm empty state |
| 8 | ChatGPT (public page) | screenshot | answer as plain text, small actions under it (copy, listen, rate) |
| 9 | Claude (public sign-in page) | screenshot | typography-led hierarchy, little chrome |
| 10 | Linear (public site) | screenshot | dense but quiet tables, status pills |
| 11 | Notion AI page | screenshot | knowledge as a searchable table with status |
| 12 | Intercom Fin page | screenshot | conversation thread with human hand-off |
| 13 | Stripe docs "Web Dashboard" | page | admin pattern: tabs inside a page, tables with filters |

**Typography decision**: Bricolage Grotesque for headings, Poppins for body. Poppins is the only candidate that ships a designed
Devanagari, so Hindi and English share one family; Bricolage is Latin-only, so Hindi headings fall back to Poppins/Noto Sans
Devanagari. Poppins is wide, so dense tables use 14–15 px; a narrower body face may suit very dense admin screens later.
