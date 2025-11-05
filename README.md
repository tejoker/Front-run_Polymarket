# 🤖 Polymarket Bot — Documentation

## 📘 Overview

Automated trading bot for **Polymarket prediction markets**, optimized for **High-Frequency Trading (HFT)** with **automatic ROI-based prioritization** and **1€ auto-execution** on the best opportunity.

> ⚠️ **Disclaimer:**
> This is a **personal training project** built to practice **Rust, C++, and quantitative logic**.
> It is **not a real trading bot**, does **not guarantee any financial results**, and should **not be used for live trading**.

---

## ⚙️ Architecture

* **C++ Backend** – Ultra-optimized trading engine (latency < 100ns)
* **Rust Frontend** – Data management and interface
* **SQLite Database** – Storage of opportunities and signals (to be optimized)
* **Polymarket API** – Real-time market data via GraphQL

---

## 🔁 Workflow

### 0. Automatic Prioritization System

* **Continuous market scanning**
* **Real-time ROI calculation** for every opportunity
* **Automatic prioritization** by descending ROI (best first)
* **Auto-execution**: 1€ instantly placed on the top opportunity
* **Conflict resolution**: In case of identical timing, the highest ROI wins

---

### 1. Data Collection

* **Polymarket Markets** via GraphQL API
* **External sources**: Fed, SEC, news outlets
* **Keyword detection**: Automatically extracts relevant terms

---

### 2. Opportunity Detection

* **Relevance scoring**: Based on keyword/source matching
* **Realistic ROI computation**: Includes fees, slippage, and fixed costs
* **Confidence thresholds**: High / Medium / Low
* **Automatic prioritization**: Sorted by descending ROI

---

### 3. Signal Generation

* **Decision logic**:

  * ROI > 2% AND confidence > 40% → **BUY**
  * ROI > 1.5% AND confidence > 35% → **SELL**
  * Else → **MONITOR**
* **Automatic prioritization**: Always selects the highest ROI
* **Auto-execution**: 1€ placed instantly on the top trade
* **Simplified system**: Only the best ROI matters

---

### 4. Position Management

* **Fixed position size**: 1€ per trade
* **Automatic prioritization**: Highest ROI wins
* **Immediate execution**: Fully autonomous
* **Simplicity**: One active trade at a time
* **Conflict resolution**: Always favor the highest ROI

---

## ⚡ HFT Optimizations

### Latency

* **ROI cache**: Avoids recomputation (< 1μs latency)
* **Precomputed tables**: Instant lookup
* **Ultra-fast decisions**: < 100ns
* **Automatic prioritization**: Instant ROI ranking

### Memory

* **Pre-allocation** of vectors
* **Auto-cleaning** to prevent fragmentation
* **Smart caching** for adaptive memory management

---

## ⚙️ Configuration

### Global Parameters

```cpp
GLOBAL_FEE = 0.03;           // 3% Polymarket fee
GLOBAL_CATCHUP_SPEED = 0.8;  // 80%/sec catch-up speed
GLOBAL_ACTION_TIME = 0.025;  // 25ms HFT latency
GLOBAL_FIXED_COST = 0.0005;  // Reduced fixed costs
```

### Monitored Sources

* Federal Reserve, SEC, BEA, NBER
* White House, Fox News, CNN
* Coinbase, Ethereum Foundation

---

## 📊 Logs & Monitoring

### Log Format

```
🚀 [EXECUTION] Automatic trade executed!
   Market: market_123
   Action: BUY
   ROI: 65.8%
   Amount: 1€
[PRIORITY] Trade prioritized: market_123 (ROI: 65.8%, Action: BUY)
[SUCCESS] 5 trading opportunities detected
```

### Metrics

* Number of detected opportunities
* Generated signals
* **Executed automatic trades**
* **ROI of top trade**
* Total PnL
* Reaction time
* **Prioritization efficiency**

---

## 🔒 Security & Validation

### Checks

* **Fixed amount**: 1€ per trade
* Valid Market ID
* **ROI prioritization**: Highest ROI auto-selected
* **Confidence thresholds** respected

### Error Handling

* API timeout (5s)
* Automatic retry
* Local cache fallback

---

## 🚀 Usage

### Compilation

```bash
cargo build --release
```

### Execution

```bash
./target/release/polymarket-bot
```

### Environment Variables

```bash
cp env.example .env
# Configure API keys and parameters
```

---

## 📈 Performance

### Target Metrics

* **Total latency**: < 100ms
* **Throughput**: 100+ markets/sec
* **ROI precision**: ±0.1%
* **Uptime**: 99.9%
* **Automatic prioritization**: < 10ms
* **Auto-execution**: < 50ms

### Monitoring

* **Real-time logs** with execution tracking
* **Performance metrics** & prioritization reports
* **Automatic alerts** for executed trades
* **Trading dashboard** displaying top ROI
* **Conflict resolution tracking**

---

*This project was developed for educational purposes only — to experiment with Rust, C++, and quantitative modeling techniques. It should not be used for real trading or investment decisions.*
