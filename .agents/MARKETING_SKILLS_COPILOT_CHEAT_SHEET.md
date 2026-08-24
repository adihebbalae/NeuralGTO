# NeuralGTO Marketing Skills — Copilot Quick Reference

TL;DR: Ask Copilot for marketing help. It automatically recognizes and applies the right skill.

---

## Quick Invoke Commands

**Copy/paste these into Copilot chat:**

### Foundation
```
/product-marketing-context

Check positioning: "Show me the product context (positioning, personas, messaging)"
```

### Writing
```
/copywriting

Examples:
- "Write copy for [landing page/button/email]"
- "Create 3 headline variants for [page]"
- "Write an outreach email to [coaches/influencers]"
```

### Conversion Optimization
```
/page-cro

Examples:
- "Optimize [page/button] for conversions"
- "Test these CTA variants: [option A], [option B]"
- "Why is our conversion rate low?"
```

### Content Strategy
```
/content-strategy

Examples:
- "What should we blog about in Q2?"
- "Create a 3-month content calendar"
- "Plan content for [feature launch]"
```

### SEO
```
/seo-audit

Examples:
- "Check SEO on [blog post/landing page]"
- "Optimize this for search"
- "What keywords should we target for [topic]?"
```

### Launch & Growth
```
/launch-strategy

Examples:
- "Plan the launch for [feature]"
- "How do we announce [release]?"
- "Create a growth strategy for [goal]"
```

---

## Smart Workflows (Copy the Full Prompt)

### Write a Landing Page
```
"I need a high-converting landing page for [feature]. 
Use the product context to inform positioning.
Then: headline variants → copywriting → CTA optimization → SEO check"

OR simpler: "Write and optimize a landing page for [feature]"
```

### Launch a Feature
```
"Plan the launch for [feature]:
1. What content should we create?
2. Write the announcement copy
3. How do we reach coaches/communities?
4. Create messaging variants"

OR simpler: "Plan a feature launch for [feature]"
```

### Improve Blog SEO
```
"Optimize this blog post for search:
1. Check SEO (title, meta, headers, keywords)
2. Improve headline if needed
3. Add internal links
4. What keywords are we ranking for?"

OR simpler: "Make this blog post SEO-friendly: [paste text]"
```

### Content Calendar
```
"Create a 3-month content calendar:
- What topics should we write about?
- What keywords do we want to rank for?
- What formats (blog, video, guides)?
- What's the posting schedule?"

OR simpler: "What should we blog about?"
```

---

## Common Requests & Expected Skill

| You Ask | Skill Applied | What You Get |
|---------|---------------|--------------|
| "Write copy for..." | copywriting | Headlines, subheadings, CTAs, messaging |
| "Optimize [page] for conversions" | page-cro | Button placement, CTA variants, testing plan |
| "Check SEO on..." | seo-audit | Title/meta/header audit, keyword analysis, ranking opportunities |
| "Plan content" | content-strategy | Blog calendar, topic ideas, content pillars |
| "Launch [feature]" | launch-strategy | Launch plan, messaging, community outreach |
| "What's our positioning?" | product-marketing-context | Personas, value props, brand voice, differentiators |

---

## Brand Voice Reminders

**NeuralGTO brand:**
- "GTO Explained. Not Memorized."
- Free, educational, precision-focused
- Speak to: tournament players, cash regulars, coaches
- Tone: Technical, helpful, no hype
- Avoid: "Win more," "beat opponents," selling (it's a study tool)

Copilot knows this. Just reference it:
```
"Write copy for [thing]. Remember our brand is precision & education, not gambling."
```

---

## Troubleshooting

**Copilot ignored my intent?**
→ Be explicit: `/copywriting` instead of "help me write something"

**Output doesn't match NeuralGTO?**
→ Ask Copilot to "Check the product-marketing-context first"

**Don't know what to create?**
→ Start with `/content-strategy` — it'll prioritize topics

**Want to test multiple options?**
→ Ask for variants: "Give me 3 CTA options" or "5 headline variants"

---

## Files to Know

- **Skills location:** `.agents/skills/[skill-name]/SKILL.md`
- **Quick start:** `.agents/MARKETING_SKILLS_QUICK_START.md`
- **Full guide:** `.agents/MARKETING_SKILLS_INTEGRATION_GUIDE.md`
- **This file:** `.agents/MARKETING_SKILLS_COPILOT_CHEAT_SHEET.md` (you are here)

---

## One-Minute Onboarding

1. **You need marketing help?** Ask Copilot. It's that simple.
2. **Copilot doesn't understand?** Type `/copywriting` (or the skill name).
3. **Want to align with positioning?** Type `/product-marketing-context` or ask Copilot to "check the context"
4. **Want a full process?** Pick a workflow above (launch, content, SEO, etc.) and paste the prompt.

---

## Pro Tips

- **Chain requests:** "Write copy → optimize page → add SEO → ready for launch"
- **Ask for variants:** Always get 3+ options before picking one
- **Reference personas:** "Write this for [tournament players/coaches/casuals]"
- **Test and iterate:** Ask for feedback frameworks, measurement plans
- **Cross-check:** After copywriting, always ask seo-audit about keywords
- **Stay aligned:** Every marketing request should reference positioning

---

## Links

- **Original repo:** https://github.com/coreyhaines31/marketingskills (for context, contributing)
- **Skills spec:** https://agentskills.io/ (how they work)
- **NeuralGTO:** https://github.com/adihebbalae/neus_nlhe

---

**Last Updated:** March 11, 2026  
**Bookmark this file!** Ctrl+K → "marketing" → Cmd+L to open it fast

