# GrowthX Buildathon Scoring Mechanisms

Source: `https://growthx.club/docs/opencode-buildathon-by-growthx-builder-handbook`

## Overview

- Teams pick one primary track: `Virality`, `Revenue`, or `MaaS`.
- Each scoring parameter is graded from `L1` to `L5`.
- Core formula: `points = (L - 1) x weight`.
- `L1 = 0 points`, `L2 = 1x weight`, `L3 = 2x weight`, `L4 = 3x weight`, `L5 = 4x weight`.
- Base score caps:
  - `Virality`: `164`
  - `Revenue`: `176`
  - `MaaS`: `164`
- Some parameters have uncapped `overflow` points beyond `L5`.
- Cross-track bonus is capped at `50` points per team.
- Rankings happen within each chosen track.

## Submission To Winners

1. `3:45 PM`: Submit live URL, repo, and track-specific evidence.
2. `3:45-4:00 PM`: Mentor nominations plus AI first-pass.
3. `4:00-4:10 PM`: Top `20` teams are locked.
4. `4:10-4:20 PM`: Pitch-down. Each shortlisted team gets a `45-60s` mentor advocacy pitch.
5. `4:30-5:15 PM`: Top `5-6` teams do live `3-minute` demos.
6. `5:15-5:30 PM`: Judge huddle and bonus application.
7. `5:30 PM`: Winners announced.

Key rule: if no mentor is willing to advocate for the project, it does not make the demo round.

## Virality

Base cap: `164 + overflow`

Notes:

- Impressions are platform-agnostic.
- Ad-driven metrics are discounted to `25%` of face value.
- Overflow exists on `impressions`, `reactions`, `visitors`, and `signups`.

| Parameter | Weight | L1 | L2 | L3 | L4 | L5 | Overflow |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Impressions and views | `1x` | Under `100` | `101-1k` | `1k-2.5k` | `2.5k-5k` | `5k-7.5k` | Beyond `10k`: `+1 pt x 1x` per extra `1,000` |
| Reactions and comments | `2x` | Under `3` | `3-10` | `11-25` | `26-50` | `51-100` | Beyond `100`: `+1 pt x 2x` per extra `10` |
| Amplification quality | `3x` | None | `1-2` peer builders engage | `3+` peer builders or `1` sub-`10k` founder/operator engages | `1` notable `10k+` founder/operator reshare | Multiple notable amplifications, PH feature, press, or known investor amplification | None |
| Visitors to product | `10x` | Under `10` | `11-50` | `51-250` | `251-1,000` | `1,000+` | Beyond `1k`: `+1 pt x 10x` per extra `100` |
| Signups or meaningful actions | `25x` | Up to `5` | `6-25` | `26-100` | `101-250` | `251-1,000` | Beyond `1k`: `+1 pt x 25x` per extra `50` |

Verification rules:

- Visitors should be shown in `Datafast`, `PostHog`, `Plausible`, or `GA4`.
- Read-only analytics access is required for full credit; otherwise visitors are capped at `L2`.
- Team members and anonymous visits do not count toward signups/actions.

### Virality Metric Notes

#### 1. Impressions and views

- This is top-of-funnel reach, not conversion quality.
- All platforms count, but paid reach is only worth `25%` of headline numbers.
- Strong performance here helps, but by itself it will not carry the track because the weight is only `1x`.

#### 2. Reactions and comments

- This measures whether the content actually caused engagement, not just passive scrolling.
- Paid engagement is also discounted to `25%`.
- The metric still matters because it signals whether the message is resonating before traffic and signups are considered.

#### 3. Amplification quality

- This is a quality metric, not a volume metric.
- A small number of credible reshares from founders, operators, investors, or Product Hunt/press can beat a larger amount of shallow engagement.
- This is the only virality metric without overflow, so it is mainly a credibility signal rather than a scale signal.

#### 4. Visitors to product

- This is where distribution starts becoming product interest.
- Because the weight is `10x`, this matters far more than impressions or reactions.
- Analytics evidence is mandatory. Without read-only access, the handbook caps this metric at `L2`.

#### 5. Signups or meaningful actions

- This is the root parameter for the track and the heaviest virality lever at `25x`.
- It is not enough to collect anonymous traffic. The product needs a real action such as signup, install, first use, or account creation.
- Team-generated signups do not count, so the product has to attract outside users.

## Revenue

Base cap: `176 + overflow`

Notes:

- This is the hardest track, so it has the highest base cap.
- Signups are the root parameter.
- Overflow exists on `signups`, `revenue generated`, and `waitlist`.
- Judging is `100% live product`, not decks.

| Parameter | Weight | L1 | L2 | L3 | L4 | L5 | Overflow |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Signups | `20x` | `0` | `1-25` | `26-100` | `101-250` | `251+` | Beyond `250`: `+1 pt x 20x` per extra `50` |
| Live product quality | `8x` | Broken | Rough MVP | Working product, does what it claims | Polished, better than alternatives | Feels `10x`, magical onboarding, doesn't look like a 4-hour build | None |
| Revenue generated (USD) | `4x` | `$0` | Up to `$25` | `$25-$100` | `$100-$500` | `$500+` | Beyond `$500`: `+1 pt x 4x` per extra `$100` |
| Waitlist | `4x` | `0` | `1-50` | `51-250` | `251-1,000` | `1,000+` | Beyond `1k`: `+1 pt x 4x` per extra `250` |
| Pain point severity | `2x` | Cannot name a user or pain | Vague persona | Named user, `1-2` conversations | Named user, `3+` confirming conversations with quotes | Named user, `5+` conversations and at least one payment-intent moment | None |
| SOM | `2x` | No math | Math attempted but wrong | Correct `users x ACV`, under `INR 10 cr` | Correct math, `INR 10 cr-INR 1,000 cr` | Correct math, over `INR 1,000 cr` with a defensible beachhead | None |
| Right to win | `2x` | Team could be anyone | Generic interest | Some domain exposure | Direct operator/domain experience | Deep founder-market fit visible in the build | None |
| Why now | `1x` | Could have been built `5` years ago | Riding general trends | Clear tailwind in last `2` years | Specific unlock in last `12` months | Window opened within `6` months and is visible in the product | None |
| Moat and defensibility | `1x` | Copyable in a weekend | Thin first-mover edge | Workflow lock-in, integrations, or taste | Data flywheel, network effects, switching costs | Compounding moat with scale | None |

Revenue qualification:

- Counts: paid product signups, usage/API fees, paid digital goods, premium upgrades.
- Does not count: consulting, agency fees, manual done-for-you work, payments from teammates, friends, or staged testers.
- Test: if the product disappears tomorrow and the revenue disappears with it, it counts.

### Revenue Metric Notes

#### 1. Signups

- This is the root parameter for Revenue and the highest-weight metric at `20x`.
- The signup must include a first-use event, not just an email capture.
- A big waitlist with weak activation helps less than actual product usage.

#### 2. Live product quality

- This is the main quality check on whether the team built a convincing product or only a demo shell.
- Judges look at time to first value, UX clarity, smoothness of the happy path, and whether the product feels differentiated.
- Because this is weighted `8x`, polish on the core user path can materially improve ranking.

#### 3. Revenue generated

- This measures actual money moved during the event through a productized flow.
- The handbook explicitly rejects service or team-powered revenue.
- The strongest interpretation is: someone paid the product, not the builders.

#### 4. Waitlist

- This is weaker than signups because it measures interest without product use.
- It still matters because it captures pre-demand and audience pull.
- Overflow exists here, but it is still lower leverage than signups because of the lower weight.

#### 5. Pain point severity

- This is a customer truth metric.
- The more concrete and recent the evidence, the better: named users, multiple conversations, direct quotes, and visible willingness to pay.
- Generic statements like "founders need better tools" land poorly here.

#### 6. SOM

- This is a bottoms-up math test, not a storytelling exercise.
- The expected formula is `target users x realistic ACV`.
- Wrong units or inflated user bases can drop the metric to `L1/L2` even if the product itself is strong.

#### 7. Right to win

- This checks founder-market fit and unfair advantage.
- The best evidence is when domain experience is visible directly in product choices, workflow understanding, or customer access.
- A team can score well here even without years in the space if it shows clear insight and proximity.

#### 8. Why now

- This tests timing quality.
- Weak answers sound like general AI enthusiasm. Strong answers point to a recent capability shift, regulation, behavior shift, or market unlock.
- Since the weight is only `1x`, this should support the story, not become the whole pitch.

#### 9. Moat and defensibility

- This asks what gets stronger if the team keeps executing.
- Taste, workflow lock-in, data loops, switching costs, and network effects all count.
- Pure first-mover advantage is explicitly weak in this rubric.

## MaaS

Base cap: `164 + overflow`

Notes:

- MaaS means `agents as employees`, not a single chatbot.
- Mentors verify by giving the team a real task and watching output land on a real surface.
- Overflow exists only on `working product shipping real output`.

| Parameter | Weight | L1 | L2 | L3 | L4 | L5 | Overflow |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Working product shipping real output | `20x` | Demo only, canned responses | Agents run but output is broken or hallucinated | Working output on staged or test surfaces only | Real output on real surfaces, but human babysitting needed | Autonomous real task completion on real live surfaces with production-quality output | Past `L5`: `+1 pt x 20x` per additional autonomous real task during judging |
| Agent org structure | `5x` | One monolithic agent | `2-3` agents with hardcoded handoffs | Manager plus specialists with static routing | Manager dynamically plans, delegates, reviews | Manager spawns specialists on the fly and agents self-adjust/escalate | None |
| Observability | `7x` | `console.log` only | Structured logs, no UI | Specific run can be inspected step by step | Trace tree, token/cost per step, filters | Run diff, alerts, searchable runs, production-grade debugging | None |
| Evaluation and iteration | `5x` | No evals | Manual spot-checks | Named eval set run manually | Automated eval pipeline blocks regressions | Closed-loop evals improve system over time | None |
| Agent handoffs and memory | `2x` | Stateless | Lossy handoffs | Short-term memory within a task | Persistent memory across tasks | Hierarchical memory: working, episodic, semantic | None |
| Cost and latency per task | `1x` | Over `30 min` or over `$5` | `10-30 min` or `$2-$5` | `5-10 min` or `$0.50-$2` | `1-5 min` or `$0.10-$0.50` | Under `1 min` and under `$0.10` | None |
| Management UI | `1x` | CLI/code only | Basic web UI | Functional PM-usable UI with docs | Clean UI, non-engineer can operate with one walkthrough | Non-engineer can onboard a new role unassisted in under `10 min` | None |

Important verification rule: staged WordPress or sandbox Gmail setups are capped at `L3` for real output.

### MaaS Metric Notes

#### 1. Working product shipping real output

- This is the root parameter and by far the most important MaaS metric at `20x`.
- The system must complete a real task in the declared domain and land output on a real surface a customer could use tomorrow.
- Staged demos, canned runs, and sandbox-only outputs are explicitly penalized.

#### 2. Agent org structure

- This measures whether the system behaves like a team, not a single wrapped prompt.
- The rubric favors manager-and-specialist structures over flat setups.
- Higher levels require dynamic planning, delegation, and role adaptation.

#### 3. Observability

- Observability is capability-based, not tool-brand-based.
- The question is whether a mentor can inspect a run, understand what happened, and debug failures quickly.
- This is the second biggest MaaS lever after real output because it carries `7x` weight.

#### 4. Evaluation and iteration

- This measures whether the team can improve the system intentionally over time.
- Manual spot checks only score low. Named eval sets and automated regression checks score higher.
- The strongest version is a closed loop where failures become future evals.

#### 5. Agent handoffs and memory

- This checks whether context survives across agents and across tasks.
- Simple handoffs are not enough if downstream agents have to rediscover context.
- Higher scores require persistent and eventually hierarchical memory.

#### 6. Cost and latency per task

- This is a practical viability metric.
- The slower or more expensive side governs the score.
- A system can be impressive, but if it is too slow or too expensive, it loses points here.

#### 7. Management UI

- This checks whether a non-engineer could actually operate the system.
- Higher scores require less team assistance and more self-serve control.
- At `L5`, a non-engineer should be able to onboard a new role in under `10` minutes without help.

## Evidence Checklist By Track

### Virality

- Analytics access for visitors.
- Public post metrics or platform screenshots for impressions and reactions.
- Screenshots or links for reshares, founder amplification, press, or Product Hunt visibility.
- Product logs or analytics events proving real signups or meaningful actions.

### Revenue

- Live product URL that works end to end.
- Signup and activation evidence.
- Payment processor evidence for revenue.
- Submission notes with customer quotes, pain evidence, and SOM math.

### MaaS

- Real task intake and real output landing on a live surface.
- Trace visibility for runs.
- Eval artifacts if claiming iteration maturity.
- A management surface if claiming non-engineer usability.

## Cross-Track Bonus

- Teams choose one primary track.
- Bonus weight is `0.5x` of the original parameter weight.
- Total bonus is capped at `50` points.
- Evidence requirements are identical to primary-track evidence rules.

| Source Track | Parameter | Original Weight | Bonus Weight | Max Bonus |
| --- | --- | --- | --- | --- |
| Virality | Signups | `25x` | `12.5x` | `50` |
| Virality | Visitors | `10x` | `5x` | `20` |
| Virality | Reactions and comments | `2x` | `1x` | `4` |
| Revenue | Signups | `20x` | `10x` | `40` |
| Revenue | Live product quality | `8x` | `4x` | `16` |
| Revenue | Revenue generated | `4x` | `2x` | `8` |
| MaaS | Real output shipping | `20x` | `10x` | `40` |
| MaaS | Observability | `7x` | `3.5x` | `14` |

## Anti-Spoof

Applies only to `Virality`.

- `Visitors` and `signups` are checked against unpublished plausibility ratios.
- Ratios include `impressions-to-visitors` and `visitors-to-signups`.
- If a team's numbers fall outside the allowed band, the affected parameter drops to `L1` unless they can show evidence of a valid off-site source.
- Accepted evidence examples:
  - newsletter analytics with open and click data
  - Product Hunt feature traffic
  - WhatsApp waitlist traffic bypassing the public URL
  - direct DM conversions with screenshots
- If both ratios trip, `2` mentors manually review the case.
- Review decisions are conservative.

## Tie-Breakers

Within a track:

1. Root parameter score
2. Live product quality score
3. Mentor panel vote

Root parameter by track:

- `Virality`: signups
- `Revenue`: signups
- `MaaS`: real output

Overall cross-track tie-breakers:

1. Highest single-track score
2. Mentor panel vote

## Strategic Takeaways

- `L3 across every parameter` is better than chasing `L5` on only one parameter.
- The recommended strategy is to get every parameter to `L3` by `2:00 PM`.
- Only after that should a team push `1-2` parameters to `L4/L5`.
- Highest-leverage parameters:
  - `Virality`: signups and visitors
  - `Revenue`: signups and live product quality
  - `MaaS`: real output and observability
- `L5` is meant to be reachable; overflow rewards breakout performance.
- Evidence matters: without proof, `L4+` claims usually cap at `L3`.
- Broken deploys kill demo chances even if the idea is strong.
- Mentor advocacy matters almost as much as raw scoring because the pitch-down decides who gets demo slots.
