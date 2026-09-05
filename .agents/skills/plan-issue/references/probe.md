# Brief, quiz, and reflect

Load this after `RESEARCH.md` and before grilling. Do not skip because
the user opened the Issue or "already knows the codebase". Write the
artifacts, then wait. Do not write `PLAN.md` in this phase unless probe
was explicitly skipped.

Invariants in `AGENTS.md` stay locked even when reflection recommends a
larger change: Python 3.14+, no legacy shims, no public security Issue,
no fork publish/docs URL claims. `AGENTS.md` is the constitution and
ADR stand-in. Do not create `CONTEXT.md` or `docs/adr/`.

Facts about this tree stay the agent's job. Do not quiz or grill a
lookup. Decisions (scope, architecture, acceptance) are the user's.

## Skip

Probe is **required** until the user waives it in this conversation.
Valid waivers name skipping the Q&A: `skip probe`, `skip quiz`,
`skip the questions`, `just write the plan`, `跳过问答`, `跳过提问`,
`直接出方案`, or a clear synonym of those. Filing a ticket, calling
the change small, or claiming tree knowledge is not a waiver.

On skip:

1. Run `python .agents/skills/plan-issue/scripts/issue_plan.py skip-probe`
   (or pass `--skip-probe` on `init` if the waiver already happened).
2. Write `BRIEF.md` from research. Do not wait for framing acceptance.
3. Write `QUIZ.md` with `**Total:** 0/10` and `**Verdict:** skipped`.
   Do not invent five questions. If some answers already exist, keep
   them and mark the rest skipped.
4. Write `REFLECT.md` with both paths. Default the recommendation to
   `surgical` unless the request already picked `better` or `stop`.
   Do not wait for a pick.
5. Write `QUESTIONS.md` with `**Probe:** skipped` and the waiver
   phrase. Score coverage from research (Clear when already answered).
   Put leftover unknowns in the plan's Open questions. Do not grill.
6. Continue to `PLAN.md`.

The hard approval gate after the plan still applies.

## Depth

Set this in `RESEARCH.md` after the coverage ledger. Probe still runs
unless the user explicitly skipped it.

| Depth     | When                                         | After probe                                              |
| --------- | -------------------------------------------- | -------------------------------------------------------- |
| `small`   | ≤3 files, one sentence of change             | Skip 2–3 approach variants. One or two tasks.            |
| `medium`  | Clear feature, under ~10 tasks               | Variants only if architecture forks.                     |
| `large`   | Multi-owner or independently testable slices | Variants required. Capability map if slices diverge.     |
| `complex` | Ambiguity, new domain, or fog past one plan  | Implicit-requirement sweep. Map fog before a giant plan. |

Safety valve: if an implicit task list would exceed five steps, write
formal tasks even if depth was `small`.

A **capability map** is vertical slices plus blocking edges, each sized
to one executor session. Do not pre-slice fog you cannot yet phrase as
a sharp question. Out of scope is not fog.

## 2. Brief

Tell the user what problem this run is actually about, in this checkout,
not a restatement of the Issue title.

Write `BRIEF.md` and paste the same short block in chat:

```markdown
# Brief

**Problem:** one paragraph: who is blocked, what fails or is missing now
**Owner:** module id + primary path from research
**Not the problem:** one or two nearby requests this Issue is not
```

Stop. Wait for the user to accept the framing, reject it, or correct it.
If they reject it, update `RESEARCH.md` / `BRIEF.md` and brief again.
Do not start the quiz on a disputed problem.

## 3. Quiz

Probe tree understanding **and** real intent. Ask **five** multiple-choice
questions, **one per message**. Ground A–D in `RESEARCH.md`. Do not ask
who owns the code; the brief already stated the owner. Do not ask
generic process trivia. Do not reveal which option is tree-correct.

Cover these five slots, adapted to this Issue:

| #   | Slot         | What the choices distinguish                              |
| --- | ------------ | --------------------------------------------------------- |
| 1   | Current path | What happens now on the relevant happy or failure path    |
| 2   | Invariant    | A do-not-restore or security lock a naive fix would break |
| 3   | Done         | Who is unblocked and one observable that proves it        |
| 4   | Wrong fix    | A related-looking change that is the wrong design here    |
| 5   | Intent       | What they actually want if it is not the ticket's patch   |

Every question is A/B/C/D. Exactly one option may be tree-correct on
slots 1–4. Put diagnostic distractors on those slots (legacy restore,
wrong layer, extra subsystem, different user-facing goal). Tag each
chosen distractor with an intent signal in `QUIZ.md`. Slot 5 has **no**
tree-correct answer: it is a preference.

Chat shape:

```markdown
After a group mention with `llm_access.group` off, what happens now?

A. ...
B. ...
C. ...
D. ...

Reply with A, B, C, or D.
```

If they type prose instead of a letter, map it to an option or ask them
to pick one. After each answer, score silently; do not debate mid-quiz
unless they ask to stop.

### Rubric

Slots 1–4 (tree):

| Score | When                                                         |
| ----- | ------------------------------------------------------------ |
| 2     | Picked the tree-correct option                               |
| 1     | Near-miss: right area, missed the invariant or path          |
| 0     | Contradicts the tree, restores a removed surface, or no pick |

Slot 5 (intent):

| Score | When                                                                               |
| ----- | ---------------------------------------------------------------------------------- |
| 2     | One clear goal (surgical patch, structural change, or a different product outcome) |
| 1     | Hedge / "both" / conflicts with their slot 1–4 signals                             |
| 0     | "Whatever the Issue says" with no preference, or refuses to pick                   |

Record **intent signals** from every answer, including 2-point tree
answers (ticket-literal is itself a signal). These feed reflection.

**Total** is `/10`. **Expected understanding** is **7/10**.

| Verdict    | Total       | Effect                                                     |
| ---------- | ----------- | ---------------------------------------------------------- |
| `pass`     | >= 7        | Issue text may stay the working spec                       |
| `fail`     | <= 6        | Do not treat the Issue body as the spec                    |
| `override` | any         | User said proceed anyway after seeing the score            |
| `skipped`  | 0 / partial | User waived probe. Issue body is not proven understanding. |

On `fail`, say which slots scored 0/1 and what the tree actually does.
Offer retry (new five) or `override`. Still run reflection: answers and
intent signals outweigh the ticket wording when they disagree.

Write `QUIZ.md`:

```markdown
# Quiz

**Total:** 6/10
**Verdict:** fail
**Intent:** wants-operator-ui; ticket-literal on path

### Question 1: Current path

**Asked:** ...
**Options:** A ... / B ... / C ... / D ...
**Answer:** C
**Score:** 0
**Intent signal:** wants-legacy-compat
**Note:** picked restore of `group_wake_policy`
```

Skipped stub:

```markdown
# Quiz

**Total:** 0/10
**Verdict:** skipped
**Reason:** user explicitly skipped probe
```

## 4. Reflect

Use `RESEARCH.md`, the accepted brief, the quiz answers, and the intent
signals. Infer the user's actual goal even when it diverges from the
Issue. Then ask whether this checkout has a better way to reach that
goal than the ticket's proposed patch.

### Job (JTBD)

State the job as **verb + object + contextual clarifier**, with no
product or proposed patch in it. Example: _record why a group message
woke the bot_, not _add a wake_reasons field_. Name the executor
(operator, plugin author, Dashboard user). The ticket text is a
solution candidate, not the job.

### Why-chain

Run Five Whys on the **request**, not only on bugs. Each why drills
into the previous answer; do not list sibling complaints. Stop at an
**executable root**: a code, test, design, or process change in this
checkout. "The Issue asked for it" is a symptom. If Why 5 is still the
ticket's patch, you stopped too early.

Keep competing intent hypotheses (`CONFIRMED` / `REJECTED` /
`UNRESOLVED`) from quiz distractors and the why-chain. The surgical
path is the proximate fix; the better path must serve the job.

### Paths

In this step, **any current-path redesign is in play**: move an owner,
delete a split, change a contract, collapse a stage, replace a store,
re-cut a Dashboard surface. Give reasons from structure, not taste.
Surgical remains the default recommendation unless a larger change
removes a real invariant violation, a duplicated owner, or a design that
cannot meet the inferred goal without more shims.

Score each candidate with the **deletion test**: if deleting the module
makes complexity vanish, it is a pass-through; if complexity reappears
across N callers, it earns its keep. Deepening pays off on **hot spots**
(`git log` files that keep changing), not cold code. **One adapter is a
hypothetical seam; two adapters make a real one.** Do not add a seam
only so a test can mock it.

Label the better path:

- **Surgical refactor:** behavior-preserving. Prefactor first, then the
  feature, in separate tasks. Do not mix them.
- **Redesign:** observable behavior changes. Say so. Prefer existing
  seams; fewer seams is better (ideally one).

Present candidates as cards, not essays:

- **Files** involved
- **Problem** (friction, shallowness, leaked seam)
- **Solution** in plain English; no new interface yet
- **Benefits** in locality, leverage, and how tests improve
- **Strength** `strong` / `worth exploring` / `speculative`

If a candidate contradicts `AGENTS.md` or a changelog fork deviation,
only surface it when the friction is real enough to reopen. Mark that
conflict on the card. Do not list every theoretical refactor those
locks forbid.

Still forbidden as "better": restoring legacy APIs, Python 3.10–3.13
branches, weakening TLS/MCP/auth/`v-html` locks, or treating upstream
artifacts as fork artifacts. Do not propose interfaces until the user
picks a card.

Write `REFLECT.md` and present it in chat:

```markdown
# Reflect

## Inferred goal

One paragraph. Job statement. Separate ticket text from what the quiz
revealed.

## Why-chain

Why 1 … Why 5. Root cause and the executable change it implies.

## Intent hypotheses

| Hypothesis           | Verdict  | Signal                   |
| -------------------- | -------- | ------------------------ |
| ticket-literal patch | REJECTED | slot 5 picked structural |

## Surgical path

The smallest current-path change that satisfies the ticket as written.
Name owners and why it is enough, or why it is not.

## Better path

The strongest alternative from whole-tree structure, including
refactors. Why it is better; what it costs; what it must not restore.

## Recommendation

`surgical` | `better` | `stop`
Reason. If quiz verdict is `fail`, say how that moved the inferred goal.

## Depth

`small` | `medium` | `large` | `complex`
```

Stop. The user picks a direction (or amends the goal). That choice is
an input to grilling, not a license to implement.

## 5. Grill

Only after brief, quiz, and reflect. Skip grilling when probe is
skipped. Otherwise ask one question at a time, and only questions that
change scope, architecture, or acceptance.

### Coverage scan

Internally score remaining unknowns Clear / Partial / Missing across:
functional scope, contracts, failure paths, invariants, integrations,
terminology, and done-when. Ask at most **five** questions, highest
**Impact × Uncertainty** first. Skip anything a grep or `RESEARCH.md`
already answered. If nothing material remains, write `QUESTIONS.md`
with `none` and go to plan.

Clarify is a completeness check, not a new spec file. A question whose
answer would not change architecture, data shape, tests, or acceptance
is deferred, not asked.

For `large` / `complex` depth, run a closing **implicit-requirement**
sweep. Each row is a requirement or `N/A because …`. Do not invent
scope to fill the table.

| Dimension              | Cover                                     |
| ---------------------- | ----------------------------------------- |
| Input bounds           | Limits, formats, sanitization             |
| Failure / partial fail | Timeouts, rollbacks, compensating cleanup |
| Auth / rate limits     | Who may call what                         |
| Concurrency            | Races, ordering                           |
| State transitions      | Valid moves, guards                       |
| External failure       | Adapter/provider/MCP down                 |
| Observability          | What a test or log must show              |

`medium` covers only dimensions obviously present. `small` skips the
sweep.

### Question kinds

Prefer a short multiple-choice when the options are known. First open
choice, if any: surgical vs better vs stop. Then walk depth-first:
finish a branch before opening another. If an answer contradicts an
earlier decision, surface the conflict and resolve it before the next
question.

| Kind        | Forcing shape                                      |
| ----------- | -------------------------------------------------- |
| Intent      | Why this job, not the nearby one?                  |
| Choice      | Why X and not Y?                                   |
| Tradeoff    | Which side, and what is the deciding constraint?   |
| Dependency  | Is the blocker locked? If not, decide that first.  |
| Uncertainty | Even at 60% confidence, what would you pick today? |
| Kill        | What evidence would make this path wrong?          |

Soft questions ("have you thought about X?") are not allowed. Follow
**tension** (contradiction, unstated assumption, avoided path) even if
it jumps the category list.

### Chat shape

```markdown
**Question:** If a group mention arrives with `llm_access.group` off, should the plan record wake reasons or leave the event asleep?

**Why it matters:** acceptance tests and the waking-check owner change with this answer.

**Recommended:** B — leave it asleep — because `AGENTS.md` already forbids implicit mention wakeup.

| Option | Description                                       |
| ------ | ------------------------------------------------- |
| A      | Record reasons and still wake                     |
| B      | Leave asleep; record nothing                      |
| C      | Leave asleep; still record the suppressed reasons |

Reply with A, B, C, or "recommended".
```

Record each Q/A in `QUESTIONS.md` immediately, including the
recommendation and whether the user took it. Do not reveal the rest of
the queue. Non-blocking leftovers become plan assumptions. If the
request still bundles independent capabilities, propose a capability
map before writing one giant plan.

Stop grilling when remaining unknowns would not change architecture or
acceptance, the user says proceed, or five questions are asked. Flag
deferred high-impact items in the plan's Open questions.

Write a coverage summary at the end of `QUESTIONS.md`:

```markdown
## Coverage

| Category      | Status                                    |
| ------------- | ----------------------------------------- |
| Functional    | Resolved / Deferred / Clear / Outstanding |
| Contracts     | …                                         |
| Failure paths | …                                         |
| Invariants    | …                                         |
| Integrations  | …                                         |
| Terminology   | …                                         |
| Done-when     | …                                         |
```

Outstanding or Deferred high-impact rows must appear in the plan's Open
questions. Do not start `PLAN.md` while a blocking contradiction is
unresolved.
