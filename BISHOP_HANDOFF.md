# Bishop migration and continuation handoff

Saved source branch: `claude-bishop-aggressive`, original repository
`awujo/practicing`. Latest implementation commit before migration:
`3fb9763ec48a97df03aa99bb0546ef0b5baf5c59`.
Destination: `thesolivag/Practice`, same Bishop branch name. Kevin's branch
must remain unchanged. This migration preserves the saved source snapshot;
it does not establish that the system is finished or profitable.
The GitHub connector imports a new snapshot commit because this workspace's
Git authentication still belongs to the suspended account. Original commit
IDs above identify provenance; the original full commit graph is not copied.
Raw extracted images left in temporary extraction directories are retained
alongside the finished contact sheets.

## Where work stopped

The most recent work optimized historical example replay without changing
strategy decisions, and made the bias display preserve unrelated opposite
scopes consistently with the entry engine. The latest local focused regression
suite passed 118 tests. It has not had a full historical rerun.

Historical teacher-example validation remains incomplete. The AUDCHF replay
run `40862692957` reached the 600-second runtime guard; no match was awarded.
Latest normal-path indexing changes are in commit `3fb9763`.
The last nested USDCAD run, `40864738971`, was launched against commit
`029e68a`; its result was not retrieved before old GitHub access returned
403 (account suspended). Do not describe that run as passing or failing.
Old Actions artifacts and secrets do not migrate with source files.

## Resume order

1. Configure the new repository's Actions secrets, using existing workflow
   declarations as the inventory. Never refresh or overwrite Kevin's shared
   cTrader tokens. Bishop uses them read-only; keep Bishop tables/settings
   separate. No credentials are included in this migration.
2. If the old account becomes available, retrieve run `40864738971` before
   repeating the nested replay. Otherwise record its result as unavailable.
3. Run the full regression suite on GitHub Actions. Heavy historical jobs
   belong on Actions, not this interactive workspace.
4. Run only `video-t3-audchf-buy-loss` through
   `bishop-primary-replay-batch.yml` to check the normal-path runtime fix.
   The workflow currently fetches old run `40782235154`; adapt that input
   acquisition to the saved `data/primary_missing_inputs/` files or upload
   equivalent inputs in this new repository before dispatching.
5. After a completed bounded replay, run the remaining firsthand cases and
   inspect genuine causal-chain mismatches, confirmation timeframe, entry,
   logical stop, target and outcome. Runtime aborts are not strategy results.

## Required strategy contract

Both key-level and liquidity bias routes must remain. The user's required
external breakout uses the last qualifying lower-timeframe A/V level known
before higher-timeframe contact: weekly to daily, daily to H4. Do not make
this optional or replace it with the latest internal break.
H4 is the vantage timeframe: inducement liquidity, key-level reaction,
confirmation on the source-used timeframe (including H2/H1/M45/M30), then
retest entry. Stops follow the actual selected confirmation, including a
later second engulfing when that is the entry pattern. Do not apply engulfing
stops to every breakout. Keep source FOREXCOM and IC Markets differences
explicit; do not force numerical matches or invent prices.

## Materials and evidence

- `knowledge-base/frames/`: extracted course, Bishop session and plug-and-play
  frames/contact sheets and timestamp indexes. Original video availability is
  not guaranteed by the extracted-frame collection.
- `knowledge-base/videos/`, `knowledge-base/study/`: transcripts and studies.
- `tests/bishop_video_breakdown_cases.json`: firsthand example inventory.
- `reports/implementation_review/primary_missing_cases_source/`: observed
  source chart evidence. Videos are primary; the PDF is student-compiled
  Bishop setups and is supplemental.
- `reports/implementation_review/github_access_block/resume.json`: detailed
  runtime evidence and stop-point record.
- `data/primary_missing_inputs/`: saved AUDCHF/NZDCHF/USDJPY H1 inputs,
  including provenance and collection status.

The nearest qualified setup liquidity target and the overall higher-timeframe
objective are separate. Profitability, full mentor matching, and final broad
backtesting have not been established. Do not confuse passing code tests with
teacher-example acceptance.
