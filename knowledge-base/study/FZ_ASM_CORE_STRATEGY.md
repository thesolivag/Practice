# FZ ASM (Asian Session Model) — Comprehensive Strategy & Mechanical Specification

> **Status:** Earlier derived draft, not a verified mechanical specification. Consult `reports/FZ_ASM_SOURCE_VALIDATION.md` for timestamped evidence, qualifications and corrections.

> **Source Material**: 8 transcribed lectures + contact sheets from release `fz-asm` on `thesolivag/Practice`.
> Videos referenced: `asm-intro-to-asm`, `asm-the-5-maps`, `asm-all-you-need-asian-map-concept`, `asm-all-you-need-asian-map-chart-work`, `asm-as-itf`, `asm-ranges-at-intermediate-timeframe`, `asm-key-level`, `asm-asm-night-live-tarding-day-one`.

---

## 0. Executive Philosophy & Strategy Overview
- **Core Concept**: FZ ASM is a **Time and Price** execution framework designed primarily around the **Asian Session** (with structural expansion extending into London/NY).
- **Core Distinction**:
  - **Market Structure** answers **HOW** the market moves (zig-zags, pullbacks, internal legs).
  - **Directional Bias / Maps** answer **WHERE** the market is going (the "FROM" and "TO").
  - **Key Levels / POIs** answer **WHERE** price reacts.
  - **The Engulfing Candle** is the **Power Unit** of the model (represents institutional volume and real market intention).
- **Primary Instruments**:
  - **JPY Crosses**: USDJPY, AUDJPY, GBPJPY, CADJPY, EURJPY, CHFJPY.
  - **Metals**: XAUUSD (Gold).

---

## 1. Timeframe Architecture (Top-Down Synchronization)

| Layer | Timeframes | Function / Purpose |
| :--- | :--- | :--- |
| **HTF (Higher Timeframe)** | Daily (`D1`), 2-Day (`2D`), 3-Day (`3D`), Weekly (`W1`) | **Directional Bias**: Identifying which of the **5 Maps** is active. Defining "Where price came FROM, and where it must go TO". |
| **ITF (Intermediate Timeframe)** | 4-Hour (`H4`), 2-Hour (`H2`), 1-Hour (`H1`) | **Range & Order Flow**: Defining the active dealing range, internal order transfers, structural alignment, and HTF POIs (Order Blocks, Breakers, Open/Close levels). |
| **LTF (Lower Timeframe / Execution)** | 15-Minute (`M15`), 10-Minute (`M10`), 5-Minute (`M5`) | **Session Timing & Trigger**: Monitoring Asian open (1:00 AM–3:00 AM), candle sweeps, CHOCH, and candlestick liquidity inducement for sniper entry. |

---

## 2. The 5 Daily Maps (Determining HTF Directional Bias)

Every trading day begins by establishing directional bias on D1/2D/3D using one of five distinct maps:

### Map 1: Structural Range (Pro-Trend BOS & Order Transfer)
- **Concept**: Price moving from structural low to structural high (bullish) or vice versa (bearish).
- **Premium vs. Discount**: Standard 50% equilibrium. Pro-trend buys occur in Discount (<50%); sells occur in Premium (>50%).
- **Order Transfer Exception**: If internal ranges show continuous order block mitigation (clean handoff of orders), price **does not need** to retrace to the 50% structural discount before expanding. The target is the opposing swing extreme.

### Map 2: Candle Range (CRT — Candle Range Theory)
- **Concept**: Price is bounded between the high and low of a benchmark daily candle range.
- **Rule**: When price sweeps one boundary (e.g. low of the candle range) and rejects/closes back inside, directional bias flips toward the **opposite boundary** (the high of the candle range).
- **Formula**: `From: Swept Boundary -> To: Opposing Boundary`.

### Map 3: Consecutive Uninterrupted Candles + Sweep
- **Concept**: A directional momentum run of uninterrupted consecutive candles (e.g. 3–5 consecutive bearish candles).
- **Rule**: When a candle sweeps the low of this uninterrupted leg and closes with a rejection wick, directional bias targets the **high of that uninterrupted leg**.

### Map 4: Candle Range Confluence with Structural POI
- **Concept**: A CRT candle range forms directly inside a discounted structural range POI / key level.
- **Rule**: Highest-probability confluence setup. The CRT sweep inside the structural POI sponsors massive expansion.

### Map 5: Rejection vs. Sweep at Range Boundaries (5A & 5B)
- **Map 5A (Pure Rejection)**: Price enters a key zone inside the range and rejects cleanly off the level without needing a liquidity sweep. Rejection alone sponsors directional continuation.
- **Map 5B (Sweep & Invalidation)**: Price pierces the level, sweeps external liquidity, and body closes back inside the level (rejection wick), invalidating continuation beyond and reversing toward the opposite target.

---

## 3. Key Levels & POI Taxonomy

FZ defines key levels mechanically:

1. **Order Block (OB)**:
   - **Bearish OB**: The last bullish/buying candle before an aggressive downward expansion.
   - **Bullish OB**: The last bearish/selling candle before an aggressive upward expansion.
   - *Preference with exceptions*: The key-level lesson initially emphasizes an FVG (1199–1205 seconds), then explicitly permits lower-probability no-FVG blocks in context (1826–2187 seconds), including nearby liquidity and higher-timeframe alignment. Do not treat this as an unconditional requirement or validate the existing body-size shortcut from it.
   - *Enhancer*: If the OB swept liquidity prior to the move, it is significantly higher probability.
2. **Breaker Block (BB)**:
   - A previously valid Order Block that was violated/broken with a **candle body close** (disrespected).
   - Once broken, it flips role: a broken bullish OB becomes a bearish resistance breaker; a broken bearish OB becomes a bullish support breaker.
3. **Open-Close Key Levels**:
   - The exact horizontal line formed by candle open/close prices (body extremes) at major pivots.
4. **The Power Unit: Engulfing Candle**:
   - Represents institutional volume and commitment.
   - When an engulfing candle forms at or after a sweep, it signals immediate directional intent, frequently negating the need for deep pullbacks.

---

## 4. The Asian Session Model (Time & Price Mechanics)

### Session Timing (Nigeria Time / UTC+1)
- **Full Window**: 1:00 AM – 7:00 AM (00:00 – 06:00 UTC).
- **Prime Volatility Window**: **1:00 AM – 3:00 AM** (00:00 – 02:00 UTC).
  - Volatility is highest at session open and gradually tapers off after 4:00 AM.

### Step 1: The Hourly Candle Sweep Trigger (H1 / H2)
- At 1:00 AM, monitor the H1 candle as it tests an established Key Level / POI.
- Look for a **Liquidity Sweep**:
  - The **1:00 AM candle sweeps the 12:00 AM candle** (or the **2:00 AM candle sweeps the 1:00 AM candle**).
  - The sweeping candle pierces with a **wick** and **closes back inside** with a noticeable rejection wick.
  - *Fallback*: If no clean sweep forms on H1, inspect the 2-Hour (`H2`) candle for a sweep. If neither sweeps, **do not force the trade**.

### Step 2: Lower Timeframe Execution (M15 / M10 / M5)
Once the H1 sweep is established, drop to M15:

- **Entry Model A (Market Shift / CHOCH)**:
  - Wait for M15 to print a Change of Character (breaking the minor swing high/low that led to the sweep).
  - Enter on the retest of the resulting M15 FVG or Order Block.
- **Entry Model B (Candlestick Liquidity Inducement)**:
  - Identify an inducement candle that approaches the key level but falls short by a few pips (leaving liquidity).
  - Place a limit order directly on the **unmitigated POI / key level immediately behind that inducement candle**.
- **Stop Loss**:
  - Placed strictly beyond the extreme wick of the H1/M15 sweep candle.
- **Take Profit**:
  - First Target: Opposing Asian session range extreme.
  - Final Target: HTF target defined by the active Daily Map (Opposing structural liquidity or daily candle high/low).

---

## 5. Algorithmic / Bot State Machine Specification

For deterministic implementation and backtesting:

```
[STATE 0: DAILY BIAS SCAN]
  -> Scan D1/2D candles for Map 1-5 patterns.
  -> Output: BIAS (BULLISH / BEARISH / RANGE), HTF_TARGET, ACTIVE_POI.

[STATE 1: ITF ALIGNMENT (H4/H2)]
  -> Confirm H4/H2 dealing range boundaries and unmitigated key levels.
  -> If price is within range equilibrium or POI, arm session watcher.

[STATE 2: ASIAN SESSION WATCHER (00:00 - 02:00 UTC)]
  -> At H1 close (01:00 UTC): Check if H1 swept previous H1 low/high at POI.
  -> If sweep confirmed with wick rejection: ARM LTF TRIGGER.

[STATE 3: LTF CONFIRMATION & EXECUTION (M15)]
  -> If M15 breaks minor structure (CHOCH) or prints inducement candle:
       Place LIMIT order at M15 POI.
       SL = Sweep extreme + 2 pips buffer.
       TP1 = Asian session opposite extreme.
       TP2 = HTF Map Target.
```

