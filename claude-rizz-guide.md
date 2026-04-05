# Claude Rizz Guide: How to Get Maximum Output

## The Power Keywords

| Pattern | What It Does | Example |
|---------|-------------|---------|
| **"Decide for me"** | Stops hedging, forces a recommendation | "Don't give options, decide the best one" |
| **"Production-ready"** | Dramatically improves code quality | "Write production-ready code with tests" |
| **"No caveats"** | Kills disclaimers | "Skip the preamble, go straight to the answer" |
| **"Be exhaustive"** | Gets longer, detailed output | "Cover every edge case. Be thorough." |
| **"Spin agents"** | Parallel processing | "Run these in background, don't block" |
| **"Pass through validator"** | Makes Claude stress-test its own advice | "Validate this plan for bottlenecks" |
| **Constraints** | Claude THRIVES on constraints | "1L in 16 days, here are my resources..." |
| **Role assignment** | Changes entire output quality | "You are a McKinsey senior partner..." |
| **"Don't hedge"** | Direct, decisive answers | "Be decisive. Recommend the best one." |
| **"Continue"** | Extends cut-off outputs | "Continue from where you left off" |
| **"Implement completely"** | No placeholder code | "No TODO comments. Write all the code." |

## Structural Tricks

### XML Tags (Claude's Superpower)
```xml
<context>I'm building a SaaS for Indian SMBs</context>
<task>Design the pricing strategy</task>
<constraints>Must be under ₹5000/mo, must beat competitors</constraints>
<output_format>Table with tiers, features, prices</output_format>
```

### Expert Panel Pattern
"Analyze this from 3 perspectives: (1) a VC evaluating market size, (2) a customer deciding to buy, (3) a competitor planning defense. Then synthesize."

### CLAUDE.md Files (Persistent Context)
- `~/.claude/CLAUDE.md` — Global rules for all projects
- `./CLAUDE.md` — Project-specific context
- Put your preferences, architecture, commands, rules here
- Claude reads these AUTOMATICALLY every session

### Memory System
- Claude Code has file-based memory at `~/.claude/projects/*/memory/`
- Everything saved persists across sessions
- "Remember this" → saves immediately
- Ask "what do you know about me?" to check

## Anthropic Social Media
- **@AnthropicAI** on Twitter/X — official account, model announcements, research
- No official "Claude" social media account
- **r/ClaudeAI** on Reddit — community hub
- Anthropic Discord for developers
- Blog: anthropic.com/research and anthropic.com/news

## Power User CLI Features
- `/init` — Auto-generate CLAUDE.md for your project
- `/compact` — Compress conversation to save context
- `/model` — Switch between opus/sonnet/haiku
- `claude -p "prompt"` — Non-interactive mode for scripts/CI
- MCP servers — Connect to GitHub, databases, monitoring tools
- Hooks — Run scripts before/after Claude actions
