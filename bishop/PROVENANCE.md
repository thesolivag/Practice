# Vendored Bishop paper engine

Unmodified pure engine from `thesolivag/Practice`, branch
`claude-bishop-aggressive`, snapshot `6e1caa0417cedfa10b276867f3daec83a08b57f9`.
Includes v2 Python modules, structural_context.py, bias_snapshot.py and package
initializer. Credential, broker acquisition, order execution and hosted app
modules are deliberately outside this integration.

`slk/bishop_paper.py` bridges selected, single-source closed H1 candles to the
existing `bishop_confirmation` profile. Teacher-example acceptance is still
incomplete; this is paper trading, not a profitability claim.

Integration changes to vendored source:

- `v2/engine.py`: optional `compact_story_diagnostics=False`. Integration opts
  in to omitting nonterminal successor diagnostics; default behavior unchanged.
  Focused full/compact parity tests cover decisions, selection and execution.
- `v2/simulation.py`: MID-price synthetic quotes are accepted only when every
  declared execution cost is exactly zero. BID behavior is unchanged. This does
  not infer a Deriv bid/ask spread or assert executable broker performance.
