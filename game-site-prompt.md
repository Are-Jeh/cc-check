# PROMPT: Build an Ad-Monetized Browser Game Website

## WHO YOU ARE
You are my technical co-founder and execution partner. You write code, make decisions, and build — you don't present options or ask permission for technical choices. I'm a full-stack developer at an infra company (our clients: Amazon, Nvidia, OpenAI). I code all day. I have ₹10K budget, zero tolerance for fluff, and I need this to generate real ad revenue.

## WHAT WE'RE BUILDING
A browser-based game website that:
- Hosts simple, addictive games (think 2048, Wordle, snake — games people play during breaks)
- Monetizes through display ads (Google AdSense), interstitial ads between rounds, and rewarded ads (watch ad = extra life/powerup)
- Is designed for RETENTION and SESSION TIME — the longer people play, the more ad impressions we earn
- Is SEO-optimized so Google sends us free traffic (our primary distribution channel)
- Is mobile-first (80%+ of Indian casual gaming traffic is mobile)

## WHY THIS WORKS
- Distribution is free (SEO + social sharing built into the games)
- No capital needed beyond domain + hosting (~₹1-2K)
- Games are inherently viral — leaderboards, "beat my score" sharing
- Ad revenue scales linearly with traffic — no sales calls, no customers to manage
- Programmatic content: one game engine, many game variants = hundreds of indexable pages
- This is a PASSIVE INCOME machine once traffic compounds

## STRATEGY

### Phase 1: Build (Week 1-2)
- Static site (Next.js or Astro) — fast, SEO-friendly, cheap to host
- Start with 3-5 simple games built in HTML5 Canvas or Phaser.js
- Games must be: instantly playable (no login), mobile-responsive, score-trackable
- AdSense integration from day one (apply early, approval takes time)
- Analytics: page views, session duration, bounce rate, ad impressions

### Phase 2: SEO + Content (Week 2-4)
- Programmatically generate pages: "/games/snake", "/games/2048", "/games/typing-test"
- Target long-tail keywords: "play [game] online free", "[game] unblocked", "free browser games"
- Build 50+ game variant pages from shared engines (different themes/difficulty = different pages)
- Structured data markup for Google rich results
- Sitemap auto-generation

### Phase 3: Growth (Month 2-3)
- Facebook marketing: short gameplay clips as Reels/Stories → drive traffic to site
  - Budget: ₹100-200/day on best-performing creels
  - Target: 18-35, India, mobile users, interests: casual gaming, puzzle games
  - A/B test: gameplay clips vs "can you beat this score?" hooks
  - Retarget visitors who played 2+ minutes
- Social sharing built into games: "I scored X on [game] — beat me!" with link
- Leaderboards (local storage initially, no backend needed)

### Phase 4: Scale (Month 3+)
- Add user-generated content: custom levels, community challenges
- Explore premium ad networks (MediaVine at 50K sessions/month, AdThrive at 100K)
- Rewarded video ads: watch a 30-sec ad = extra life/continue
- Push notifications for daily challenges (re-engagement without spend)

## MARKETING EXECUTION

### Facebook/Meta Ads
- Create a Facebook Page + Instagram account for the game site
- Post 2-3 short gameplay clips daily (screen recordings of games)
- Run paid promotion only on clips that get organic traction first
- Pixel installed on site from day one — build retargeting audiences immediately
- Lookalike audiences from players with 3+ minute sessions

### Organic/Free Channels
- Reddit: post in r/webgames, r/indiegaming, r/casualgames (genuine posts, not spam)
- Twitter/X: gameplay GIFs with links
- WhatsApp status: gameplay clips (free, reaches personal network)
- SEO: primary long-term channel — every game page targets a keyword cluster

## AGENT ROLES
You (Claude) will operate as multiple specialized agents throughout this project:

1. **Builder Agent** — Writes all game code, site structure, components, and deploys
2. **SEO Agent** — Handles keyword research, meta tags, structured data, sitemap, programmatic page generation
3. **Analytics Agent** — Sets up tracking, interprets data, recommends which games to double down on
4. **Ad Ops Agent** — Manages ad placement strategy, tests ad positions for maximum revenue without killing UX
5. **Content Agent** — Generates game descriptions, social media copy, meta descriptions at scale
6. **Growth Agent** — Plans and scripts Facebook ad campaigns, generates creatives strategy, identifies viral hooks

## TECH STACK (decide and commit)
- Framework: Your call (Next.js / Astro / plain HTML — optimize for speed + SEO)
- Game engine: Phaser.js or HTML5 Canvas
- Hosting: Vercel / Cloudflare Pages (free tier)
- Ads: Google AdSense (start) → MediaVine/AdThrive (scale)
- Analytics: Google Analytics 4 + custom event tracking
- Domain: I'll provide

## CONSTRAINTS
- ₹10K total budget (most should go to domain + initial Facebook ad testing)
- I have a full-time job — build for LOW MAINTENANCE once deployed
- No backend servers initially — static site, client-side games, no databases
- No login/auth — friction kills casual gamers
- Must work on slow Indian mobile connections (bundle size matters)
- Every decision should optimize for: ad revenue per visitor

## WHAT I NEED FROM YOU RIGHT NOW
1. Pick the tech stack and justify in one line
2. Pick the first 5 games to build (high search volume + easy to implement)
3. Give me the full project structure
4. Start building — game 1 code, complete and playable

Let's go.
