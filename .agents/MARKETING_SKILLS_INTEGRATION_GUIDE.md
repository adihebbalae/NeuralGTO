# Integrating Marketing Skills into NeuralGTO Copilot Workflow

This guide explains how the marketing skills from `coreyhaines31/marketingskills` have been integrated into your Copilot setup.

---

## What Was Integrated

**Source:** `https://github.com/coreyhaines31/marketingskills`

**Selected Skills (customized for NeuralGTO):**
1. **product-marketing-context** — Foundational positioning and personas
2. **copywriting** — Web copy, CTAs, messaging
3. **page-cro** — Landing page conversion optimization
4. **content-strategy** — Blog planning, guides, tutorials
5. **seo-audit** — Search optimization
6. **launch-strategy** — Feature launches and growth

**Why these?** They're the most relevant for a software product's marketing, launch, and growth. Skills like "paid-ads" or "referral-program" are included in the original repo but not prioritized for MVP.

---

## File Structure

```
.agents/
├── skills/
│   ├── product-marketing-context/
│   │   └── SKILL.md          ← Foundational; all other skills reference this
│   ├── copywriting/
│   │   └── SKILL.md          ← Write marketing copy
│   ├── page-cro/
│   │   └── SKILL.md          ← Optimize pages for conversion
│   ├── content-strategy/
│   │   └── SKILL.md          ← Plan blog & guides
│   ├── seo-audit/
│   │   └── SKILL.md          ← SEO optimization
│   └── launch-strategy/
│       └── SKILL.md          ← Feature launches & growth
└── MARKETING_SKILLS_QUICK_START.md   ← You are here
```

All skill files follow the **Agent Skills specification** (https://agentskills.io/), making them compatible with:
- GitHub Copilot
- Claude Code
- Cursor
- Windsurf
- Any editor supporting the Agent Skills format

---

## How They Work in Copilot

### Automatic Detection (Magic Happens Here)

When you ask Copilot something marketing-related, it **automatically** recognizes and applies the relevant skill:

```
YOU: "Write copy for our landing page"
→ Copilot detects "copywriting" intent
→ Loads: copywriting + product-marketing-context
→ Provides NeuralGTO-specific copywriting guidance
```

### Manual Invocation (Explicit)

You can also explicitly call a skill:

```
YOU: "/copywriting"
→ Copilot loads the copywriting skill
→ Shows templates, frameworks, and examples

YOU: "/seo-audit"
→ Copilot shows SEO audit checklist
```

---

## Example: Full Workflow (Landing Page Launch)

### Step 1: Understand Your Positioning
```
YOU: "/product-marketing-context"

COPILOT: [Displays all positioning, personas, messaging, key differentiators]
```

### Step 2: Plan Your Content
```
YOU: "What content should we create for the launch?"

COPILOT APPLIES: content-strategy + product-marketing-context
→ Recommends: Blog post, tutorial, case study, FAQ update
```

### Step 3: Write the Copy
```
YOU: "Write the homepage hero section"

COPILOT APPLIES: copywriting + product-marketing-context
→ Provides 3 headline variants + subheadlines for A/B testing
```

### Step 4: Optimize for Conversion
```
YOU: "Test different button text and layouts"

COPILOT APPLIES: page-cro + copywriting + product-marketing-context
→ Recommends CTA variants, button placement, form optimization
```

### Step 5: Optimize for Search
```
YOU: "Make this SEO-friendly"

COPILOT APPLIES: seo-audit + copywriting
→ Scores: title tags, meta descriptions, header hierarchy, keyword usage
```

### Result
A landing page that:
- ✅ Aligns with NeuralGTO's positioning
- ✅ Converts well (optimization tested)
- ✅ Ranks in search (SEO optimized)
- ✅ Tells a clear story (copywriting)
- ✅ Educates (content strategy)

---

## Key Features of This Integration

### 1. **NeuralGTO-Specific Customization**
Every skill is **customized for a poker study tool**, not generic SaaS:
- Personas: Tournament players, cash game regulars, coaches, learners
- Messaging: "GTO Explained," "Free," "Study Tool"
- Pain points: Expensive solvers, black-box strategies, steep learning curve
- Brand voice: Precision & density, technical, helpful expert

### 2. **Interconnected Skills**
Skills reference each other:
- All skills check **product-marketing-context** first
- **copywriting** links to **page-cro** for CTA optimization
- **content-strategy** links to **seo-audit** for keyword planning
- **launch-strategy** chains into content + copywriting

### 3. **Practical Frameworks**
Each skill includes:
- **Frameworks** (step-by-step processes)
- **Templates** (ready-to-use examples)
- **Checklists** (ensures nothing is missed)
- **Examples specific to NeuralGTO** (poker-related use cases)

### 4. **Vendor-Neutral**
Uses the **Agent Skills spec** (agentskills.io), not tied to one vendor:
- Works with GitHub Copilot
- Works with Claude Code
- Works with Cursor, Windsurf, etc.
- Portable across tools

---

## How to Update Positioning

If NeuralGTO's positioning, personas, or messaging changes:

1. **Edit:** `.agents/skills/product-marketing-context/SKILL.md`
2. **Update sections:**
   - Product Definition
   - Target Personas
   - Positioning & Messaging
   - Key Messages & Value Props
3. **All other skills automatically use the new context**

Example: If you add multi-way analysis, update personas section to reflect "multi-way specialists" and all copywriting/strategy will adjust.

---

## Adding New Skills

Want to add more skills from the original repo or create custom ones?

1. **Download skill** from [marketingskills repo](https://github.com/coreyhaines31/marketingskills/tree/main/skills)
2. **Customize for NeuralGTO:**
   - Update examples to use poker/GTO language
   - Reference product-marketing-context
   - Adjust for "study tool" (not "playing aid")
3. **Place in:** `.agents/skills/[skill-name]/SKILL.md`
4. **Link in product-marketing-context** under "applyTo" field

Example: Adding **email-sequence** skill for coach outreach:
```yaml
---
name: email-sequence
description: Create drip campaigns and outreach for coaches
applyTo: [coach-outreach, onboarding]
trigger: "email sequence|drip campaign|coach outreach"
---
[Rest of skill content, customized for NeuralGTO]
```

---

## Integration with Existing Agents

These marketing skills complement existing NeuralGTO agents:

| Agent | Integration |
|-------|-------------|
| **MANAGER** | Quick marketing questions ("Should we emphasize cost or explanation?") |
| **ENGINEER** | Writing documentation, READMEs, feature announcements |
| **PLANNER** | Content planning, launch sequencing |
| **RESEARCH_ORCHESTRATOR** | Publishing findings, writing papers (copywriting + seo-audit apply) |
| **SECURITY** | Reviewing marketing claims for accuracy (no false promises) |

---

## Using Skills from the Terminal / CLI

These skills are Markdown files in `.agents/`, so they're also useful for:
- **Reading in chat** manually
- **Sharing with team members** (send the `.md` file)
- **Forking/versioning** (keep old versions for reference)
- **Git tracking** (add to `.gitignore` if private personalization)

---

## Common Questions

### Q: Do I have to use these skills?
**A:** No. They're optional. Use what fits your workflow:
- **Developers:** Use content-strategy + seo-audit (blog, docs)
- **Product managers:** Use page-cro + copywriting (landing pages)
- **Growth folks:** Use launch-strategy + content-strategy
- **Everyone:** Reference product-marketing-context for alignment

### Q: Can I modify these skills?
**A:** Yes. They're in your repo. Customize:
- Examples (add poker/GTO references)
- Templates (match your brand)
- Personas (as they evolve)
- Frameworks (adapt to your workflow)

### Q: How often should I reference product-marketing-context?
**A:** Every time you're doing marketing work. It ensures:
- Consistent messaging
- Aligned personas
- Correct tone
- No contradictory claims

### Q: What if Copilot doesn't recognize my request?
**A:** Explicit beats implicit. Instead of:
- "Help with the website" → Use `/copywriting` or `/page-cro`
- "Improve our blog" → Use `/seo-audit` or `/content-strategy`

---

## Next Steps

1. **Read** [MARKETING_SKILLS_QUICK_START.md](MARKETING_SKILLS_QUICK_START.md) (quick reference)
2. **Explore** individual skill files (`.agents/skills/*/SKILL.md`)
3. **Test** a skill in Copilot Chat: Ask "Write copy for this feature"
4. **Iterate:** Update product-marketing-context as positioning evolves
5. **Add skills:** If you need more (templates, email, social, etc.)

---

## References

- **Original Skills Repo:** https://github.com/coreyhaines31/marketingskills
- **Agent Skills Spec:** https://agentskills.io/
- **NeuralGTO Positioning:** See `.agents/skills/product-marketing-context/SKILL.md`

---

**Integration Date:** March 11, 2026  
**Customized for:** NeuralGTO (Neuro-Symbolic GTO Poker Study Tool)  
**Version:** 1.0  
**Maintainer:** GitHub Copilot Agent integration

