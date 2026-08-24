---
name: product-marketing-context
description: Create or update the product marketing foundation that all other marketing skills reference. Required for all marketing work on NeuralGTO.
applyTo: [copywriting, page-cro, seo-audit, sales-enablement, launch-strategy, content-strategy]
---

# NeuralGTO Product Marketing Context

**Document purpose:** This file establishes the product positioning, user personas, and messaging framework for all marketing work. Every marketing skill references this before taking action.

**When to use:** Create or update this file when starting any marketing initiative, and refer to it before copywriting, landing page optimization, SEO work, or launch strategy.

---

## Product Definition

**Name:** NeuralGTO  
**Tagline:** Neural-symbolic GTO poker study tool combining AI reasoning with game theory optimal solving  
**Type:** Educational software / Poker study tool  
**Primary Use Case:** Poker players analyzing hands and developing GTO-informed strategies  

**What it does:**
- Accepts natural language poker hand descriptions from users
- Parses scenarios via Google Gemini LLM
- Solves using TexasSolver (CFR-based Game Theory Optimal algorithm)
- Extracts and explains GTO strategy with exploit-ability guidance
- Provides exploitative deviations based on opponent tendencies

**Why it matters:**
GTO (Game Theory Optimal) poker is notoriously difficult to learn from books and videos. Existing tools (PioSOLVER, GTO Wizard) are expensive ($500–$1500/year), complex, and don't explain *why* a frequency exists. NeuralGTO is free, conversational, and explains the reasoning behind GTO frequencies.

---

## Target Personas

### 1. **Aspiring Tournament Player** (40% of audience)
- **Goal:** Break into mid-stakes tournaments, improve winrate
- **Pain:** Frustrated with variance; wants to understand optimal play, not just memorize charts
- **Motivation:** Compete seriously; self-improvement through study
- **Where they hang out:** Reddit r/poker, Discord poker communities, YouTube poker educators
- **Budget:** Minimal; prefers free tools
- **Technical ability:** Moderate (comfortable with Discord bots, Discord, basic CLI)

### 2. **Cash Game Regular** (35% of audience)
- **Goal:** Exploit weak opponents while maintaining +EV fundamentals
- **Pain:** Knows GTO doesn't always win (need exploits); tired of paying for solver subscriptions
- **Motivation:** Profitable play; deeper understanding of the game
- **Where they hang out:** Poker Discord communities, /r/poker, Twitch streams, coaches' materials
- **Budget:** Will pay for quality; exploring free alternatives first
- **Technical ability:** High (understands solvers, equity calculations, game theory)

### 3. **Coach / Content Creator** (20% of audience)
- **Goal:** Teach students sound GTO fundamentals; create educational content
- **Pain:** Solver costs prohibit scaling education; need tools that explain, not just solve
- **Motivation:** Authority, student outcomes, sustainable teaching model
- **Where they hang out:** YouTube, Twitch, coaching communities, Discord
- **Budget:** Professional tools are justified investment
- **Technical ability:** Very high (understands poker deeply, likely Python/tech savvy)

### 4. **Casual Learner** (5% of audience)
- **Goal:** Understand poker better; improve recreationally
- **Pain:** Intimidated by technical jargon; wants quick, accessible learning
- **Motivation:** Hobby; fun with friends
- **Where they hang out:** Reddit, casual Discord, how-to blogs
- **Budget:** Free only
- **Technical ability:** Low; needs simple interfaces

---

## Positioning & Messaging

### Core Positioning
**"GTO explained, not memorized. Neuro-symbolic poker study for anyone."**

Competitive alternatives:
- **PioSOLVER:** Expensive ($1500/yr), powerful, requires expertise
- **GTO Wizard:** Expensive ($300/yr), polished UI, precomputed charts
- **Free LLM:** ChatGPT can discuss poker but doesn't understand equity or solver output

**NeuralGTO's unique angle:**
- Free and open
- Explains *why* a frequency exists (blocker theory, range balance, board texture)
- Combines neural (LLM reasoning) + symbolic (GTO solver) for best of both
- Conversational interface (natural language input, not spreadsheets)
- Web-based and offline-capable (no subscription lock-in)

---

## Key Messages & Value Props

### 1. **Democratizes GTO**
> "Professional-grade GTO solving for poker players without professional-grade budgets."

- Solves specific hands fast
- No subscription required
- Accessible to beginners and regulars alike

### 2. **Explains, Doesn't Just Solve**
> "See the strategy. Understand why. Know when to deviate."

- Frequency breakdowns
- Blocker logic
- Exploit vulnerability explanations
- Confidence gradients

### 3. **Study Tool, Not Bot**
> "For learning. For improvement. Not for playing."

- Educational focus
- Compliance-friendly (not a real-money playing aid)
- Encourages thinking, not copy-pasting

### 4. **Fast & Conversational**
> "Describe your hand in English. Get GTO strategy in seconds."

- Natural language input (no spreadsheet syntax)
- Real-time feedback
- Mobile-friendly web interface

---

## Audience Pain Points & Solutions

| Pain | Solution | Value Prop |
|------|----------|-----------|
| Solver software is expensive | Free/open-source | Accessibility |
| Solvers don't explain *why* | Gemini + TexasSolver combo | Understanding |
| Learning GTO is overwhelming | Conversational interface | Approachability |
| Takes forever to analyze a hand | Fast web interface | Efficiency |
| Solver syntax is complicated | English-language input | Usability |
| Can't trust LLM poker advice alone | CFR-backed GTO solving | Credibility |

---

## Product Positioning Map

```
Academic (Theory-Heavy) ←→ Practical (Applied)
GTO Wizard, PioSOLVER ←→ NeuralGTO ←→ YouTubers, Blogs

Expensive ←→ Free/Affordable
PioSOLVER ($1500/yr) ←→ NeuralGTO (Free) ←→ ChatGPT

Complex ←→ Simple
TexasSolver CLI ←→ NeuralGTO (Web UI) ←→ Casual poker apps

Black-Box ←→ Explained
GTO Wizard (shows frequency) ←→ NeuralGTO (shows *why*) ←→ YouTube tutorials (subjective)
```

**NeuralGTO occupies:** Practical + Free + Simple + Explained = Unique position

---

## Brand Voice & Tone

- **Tone:** Precision & density (data-heavy, technical, minimal fluff)
- **Audience language:** Poker jargon OK for experienced players; explain terms for learners
- **Personality:** Helpful expert, not salesly; confident without ego
- **Key phrases:**
  - "Game Theory Optimal"
  - "EV-positive" / "Expected Value"
  - "Blocker logic"
  - "Frequency" / "equity realization"
  - "Exploit vulnerability"

---

## Marketing Channels & Tactics

### 1. **Community Presence** (Priority)
- Reddit: r/poker, r/poker_strategy
- Discord: Poker strategy communities, coaching servers
- YouTube comments on poker education videos
- Twitch streams (poker educators)

### 2. **Content Marketing** (Priority)
- Blog: GTO explanations, hand breakdowns, exploit vulnerabilities
- Guides: "GTO 101," "How to analyze your own hands," "Common exploits"
- Case studies: Professional player analysis

### 3. **Organic Search** (Medium)
- SEO for: "free GTO solver," "explain poker strategy," "how to analyze a poker hand"
- Optimize for AI search: LLMs cite our educational content

### 4. **Product Launches** (Low)
- Feature announcements in poker Discord channels
- Blog post for new capabilities (e.g., preflop charts, multi-way analysis)

---

## Success Metrics

### Awareness
- Monthly unique users: 500+ in Y1
- Community mentions (Reddit, Discord)
- Organic search traffic

### Engagement
- Hands analyzed per user per month: 10+
- Return visitor rate: 30%+
- Average session length: 5+ minutes

### Retention
- Users coming back 2+ weeks later: 20%+
- Email subscription growth (if launched)

### Conversion (future: sponsorship/consulting)
- Coach referrals from product
- Speaking opportunities
- Sponsorship interest from poker platforms

---

## Messaging Templates

### For Landing Page
```
Tagline: "GTO Explained. Not Memorized."

Headline: Neural-Symbolic Poker Study for Everyone
Body: Analyze your hands like a pro. Understand why frequencies exist. Learn when to exploit.

CTA: "Analyze a Hand" (primary) | "Read Guides" (secondary)
```

### For Social Media
```
# Short (Twitter/X)
"Analyze poker hands in English. Get GTO strategy with the reasoning. Free. No signup. neuralgto.com"

# Long (LinkedIn/Reddit)
"Tired of paying $500/year for a solver that doesn't explain itself? We built NeuralGTO as the free alternative that actually teaches you *why* frequencies exist."

# Discord
"Just analyzed this tournament hand with GTO reasoning... [details] Want to try? neuralgto.com"
```

### For Sales/Coaching Outreach
```
Subject: Free GTO tool for your students
Body: Hi [Coach],

Your students are stuck memorizing frequencies. What if they could understand GTO in English instead?

NeuralGTO solves specific hands, explains the logic, and highlights exploits — at zero cost. Perfect for: prep-work, student explanations, content.

Would love your feedback. Free beta access: [link]

—The NeuralGTO team
```

---

## Competitive Differentiation

| Feature | NeuralGTO | GTO Wizard | PioSOLVER |
|---------|-----------|-----------|-----------|
| Cost | Free | $300/yr | $1500/yr |
| Interface | Web + CLI | Web | Desktop |
| Explanation | *Why* frequencies (AI) | Frequencies only | Technical docs |
| Speed | Seconds | Instant (precomputed) | Minutes–hours |
| Customization | Limited | Limited | Extensive |
| Learning focus | Yes | No | No |

**Win against:** Anyone comparing price or wanting explanation  
**Lose against:** Users needing 4+ player analysis or extreme customization

---

## Roadmap (Marketing Perspective)

### Phase 1 (Now): Build Authority
- Guest posts on poker education blogs
- Community presence (subreddit, Discord)
- Free tools + generous documentation
- Case studies of interesting hands

### Phase 2 (6 months): Affiliate / Sponsorship
- Partner with poker coaches / YouTube educators
- Sponsorship from poker platforms (Upswing, Run It Once)
- Referral program for coaches

### Phase 3 (12 months): Monetization (If Needed)
- Premium features: multi-way analysis, saved hand library, coaching dashboards
- Consulting for poker platforms
- Educational content licensing

---

## References & Context

- **Product repo:** [NeuralGTO GitHub](https://github.com/adihebbalae/neus_nlhe)
- **Live site:** (Once deployed)
- **Competitive tools:** GTO Wizard, PioSOLVER, Hold'em Resources (HRC)
- **Target communities:** r/poker, Upswing Poker Discord, various YouTube channels

---

## Instructions for Marketing Skills

**When using any marketing skill (copywriting, page-cro, seo-audit, etc.):**

1. Read this file first
2. Apply positioning: "Free + Explained + Simple = Differentiator"
3. Speak to personas: Aspiring tournament players and cash game regulars are primary
4. Use brand voice: Precision, technical accuracy, helpful expert tone
5. Reference success metrics where relevant
6. Avoid: "Play poker better" language (we're a *study* tool, not a playing aid)

