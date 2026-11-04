Bishop versus Kevin: concrete build status

Inspected local origin/claude-kevin-king and the Bishop branch on2026-10-26. Code presence and configured runtime are distinguished from verified trading behavior or confirmed service availability.

| Stage | Kevin branch | Bishop branch |
| --- | --- | --- |
| Bias / story | slk/story.py,slk/standing.py | bishop/v2/stories.py, with structure and weekly context |
| Entry detection | slk/entry.py | bishop/v2/entries.py |
| Stop and target plan | Entry models and story objectives | bishop/v2/risk.py |
| Historical execution / tracking | Backtest modules | bishop/v2/simulation.py; fills, exits, cancellation, censoring |
| Stored results and viewer | webapp/app.py and static viewer | bishop/paper_store.py,bishop/webapp.py,bishop/web/; offline paper viewer |
| Operating integration | slk/live.py; webapp endpoints; render.yaml configured for Kevin branch | No continuously running v2 detector; no active broker execution; no Render configuration in this branch |
| Teacher-example validation | Not re-audited here | Not established across40 frozen examples; two recent examples still have chart-identity mismatches |

The Bishop core is implemented; that does not mean the full operational system is finished or that its bias/confirmation decisions faithfully reproduce every teaching. The previous work overemphasized strict price/chart matching and reporting while leaving the practical state unclear.

The supplied PDF and PNGs are static rendered documents, not HTML source. They illustrate the first chronological same-timeframe candidate for each of the two source examples, not the best outcome. Interactive HTML retains all61 candidate views for browser use. No new detection or historical execution was run to export these documents.
