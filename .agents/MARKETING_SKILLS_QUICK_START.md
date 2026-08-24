---
name: marketing-skills
description: Marketing skills collection for NeuralGTO — copy, conversion, content, SEO, and growth strategy.
---

# NeuralGTO Marketing Skills Registry

This is the central registry for all marketing-focused skills integrated into NeuralGTO's Copilot workflow.

## What Are These Skills?

Marketing skills are specialized Copilot instructions that help you:
- **Write persuasive copy** (copywriting)
- **Optimize pages for conversions** (page-cro)
- **Plan educational content** (content-strategy)
- **Improve search visibility** (seo-audit)
- **Launch features & grow** (launch-strategy)
- **Understand your product positioning** (product-marketing-context)

Each skill is a `.md` file in `.agents/skills/` that Copilot recognizes and applies automatically when relevant.

---

## Skill Inventory

### Foundation
| Skill | Purpose | Use When |
|-------|---------|----------|
| **product-marketing-context** | Positioning, personas, messaging framework | Before any marketing work; referenced by all other skills |

### Core Skills
| Skill | Purpose | Use When |
|-------|---------|----------|
| **copywriting** | Write landing page copy, CTAs, emails, messaging | Writing or rewriting web copy, creating marketing messages |
| **page-cro** | Optimize pages for conversion | Improving landing page performance, A/B testing, buttons/CTAs |
| **seo-audit** | Audit & optimize for search engines | Improving Google ranking, blog SEO, content optimization |
| **content-strategy** | Plan educational & marketing content | Creating blog calendars, guides, content planning |
| **launch-strategy** | Plan feature launches & growth | Announcing features, coordinating release campaigns |

---

## Quick Start: How to Use These Skills

### In Copilot Chat

**Automatic Invocation** (Copilot recognizes your intent):
```
"Help me write copy for our landing page"
→ Copilot automatically applies: copywriting + page-cro skills

"Optimize this page for conversions"
→ Copilot automatically applies: page-cro skill

"Create a 3-month content strategy"
→ Copilot automatically applies: content-strategy skill

"Check our SEO on this blog post"
→ Copilot automatically applies: seo-audit skill
```

**Manual Invocation** (Explicit skill call):
```
/product-marketing-context
→ Shows positioning, personas, messaging framework

/copywriting
→ Detailed guide to writing NeuralGTO copy

/page-cro
→ CRO tactics specific to NeuralGTO

/content-strategy
→ Full content calendar & strategy framework

/seo-audit
→ SEO checklist and optimization guide

/launch-strategy
→ Feature launch planning & execution
```

---

## Skill Relationships

All marketing skills reference the **product-marketing-context** skill, which establishes:
- **Positioning:** "GTO Explained. Not Memorized."
- **Personas:** Tournament players, cash game regs, coaches, learners
- **Brand voice:** Precision & density, technical, helpful expert
- **Key messages:** Democratized GTO, explained not just solved, study tool

When you invoke any skill, Copilot loads this context and applies it automatically.

## Skill Flows (Recommended Workflows)

### Workflow 1: Launch a Blog Post
```
1. content-strategy → Plan what to write
2. copywriting → Draft the post
3. seo-audit → Optimize for search
4. Result: SEO-optimized, persuasive blog post
```

### Workflow 2: Optimize Landing Page
```
1. product-marketing-context → Review positioning
2. copywriting → Rewrite copy
3. page-cro → Test button, headline variants
4. seo-audit → Improve for search
5. Result: High-converting, discoverable landing page
```

### Workflow 3: Plan a Feature Launch
```
1. launch-strategy → Create launch plan
2. content-strategy → Plan launch content (blog, video, etc.)
3. copywriting → Write announcement copy
4. page-cro → Optimize feature page
5. Result: Coordinated, multi-channel feature launch
```

### Workflow 4: SEO-First Content Plan
```
1. seo-audit → Identify keyword gaps
2. content-strategy → Plan content to fill gaps
3. copywriting → Write the blog posts
4. Result: Organic traffic growth strategy
```

---

## Example Conversations

### Example 1: "Write Copy"
```
YOU: "I need a new homepage headline. Our old one isn't resonating."

COPILOT APPLIES: copywriting + product-marketing-context

COPILOT:
"I'll write homepage headline variants for NeuralGTO. 
Let me check the positioning framework first...

[Product-Marketing-Context loaded: 'GTO Explained. Not Memorized.' positioning]

Here are 3 headline variants to test:

1. Problem-focused: 'Tired of paying $300/year for a GTO solver?'
2. Benefit-focused: 'Understand GTO. Actually.'
3. Speed-focused: 'GTO Analysis in Seconds'

Which resonates most? Want me to draft companion copy and CTAs?"
```

### Example 2: "Optimize This Page"
```
YOU: "Our landing page converts at 2%. Can you help improve it?"

COPILOT APPLIES: page-cro + copywriting + product-marketing-context

COPILOT:
"2% is low for a high-intent page. Let me audit it...

[Findings from page-cro framework]

I see 3 quick improvements:
1. CTA text weak ("Get Started" → "Analyze a Hand")
2. Value prop buried (move above fold)
3. Trust signal missing (add 'Free. No signup.')

Trust testing these variants:
- Variant A: Problem-focused hero + Strong CTA
- Variant B: Benefit-focused hero + Social proof
- Variant C: Speed-focused hero + Example hand

Ready to implement? Or want me to write new copy first?"
```

### Example 3: "Plan Content"
```
YOU: "What should we blog about in Q2?"

COPILOT APPLIES: content-strategy + seo-audit + product-marketing-context

COPILOT:
"Let me check keyword opportunities and your content pillars...

[Content-Strategy framework loaded]

Based on SEO research, here's Q2 content plan:

Month 1: Foundation
- 'What is GTO Poker?' (target: GTO beginners)
- 'How to Read Solver Output' (series)
- [Hand case study] (target: community)

Month 2: Application
- 'Blocker Logic Explained' (deep-dive)
- 'Equity Realization & Position' (with examples)

Month 3: Growth
- 'Free GTO vs. Paid Solvers' (vs. competition)
- Coach roundtable or guest post

This targets high-intent keywords and community engagement.
Ready to draft blog post outlines?"
```

---

## Tips for Effective Skill Use

### ✅ Do This
- **Ask specific questions:** "Write a homepage hero" beats "Help me with marketing"
- **Provide context:** "I want to target tournament players" focuses the output
- **Chain skills:** Ask for content strategy → copywriting → SEO audit in sequence
- **Test variants:** Ask for 3 CTA options, not just 1
- **Reference personas:** "Write this for coaches" vs. "Write this for players"

### ❌ Avoid This
- **Generic prompts:** "Help with marketing" (too broad)
- **Ignoring context:** Skipping product-marketing-context → misaligned output
- **One-off asks:** Asking for copy without strategy → inefficient
- **Siloed thinking:** Copywriting without SEO optimization

---

## Skill Troubleshooting

**Q: Copilot isn't recognizing my intent**
A: Be explicit: Use skill name `/copywriting` if Copilot misses the intent

**Q: The output doesn't fit NeuralGTO's voice**
A: Reference product-marketing-context first: "Check the brand voice/positioning context before writing"

**Q: These skills are for marketing, but I'm a developer**
A: That's OK! Developers often write documentation, READMEs, and feature announcements. These skills help with that clarity.

**Q: Do I have to use all of these?**
A: No. Use what fits your workflow. Developers often skip copywriting/page-cro; focus on content-strategy/seo-audit instead.

---

## Extending These Skills

The marketing skills are built to be customized. You can:
- **Update personas** in product-marketing-context if targeting changes
- **Add new skills** for specific workflows (e.g., email-sequence, partner-outreach)
- **Modify templates** to match your evolving brand voice
- **Link to new content** as your site grows

For advanced customization, see `.agents/skills/agent-customization/SKILL.md`.

---

## Further Learning

For more context on marketing skills:
- See individual skill files in `.agents/skills/`
- Original framework: https://github.com/coreyhaines31/marketingskills
- Skill specification: https://agentskills.io/

---

## Support

Questions? Ideas?
- Check the skill's own `.md` file for detailed guidance
- Refer to product-marketing-context for positioning questions
- Submit feedback to improve these skills

---

**Last Updated:** March 11, 2026  
**Skills Version:** 1.0 (NeuralGTO customized)  
**Source:** Integrated from coreyhaines31/marketingskills

