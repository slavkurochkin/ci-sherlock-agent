# LinkedIn Post

---

For years I worked with Playwright. And for years I heard the same questions from management:

"Why are tests failing again?"
"Can we improve the reliability of the framework?"
"How do we know if we're ready to release?"

Every time, the answer was the same manual process — scan the failure, scan the diff, form a hypothesis, dig into the logs. And the more PRs you have, the more that process doesn't scale.

So when I was preparing for an interview recently and got bored reading through Playwright docs I'd already used a hundred times — I built the tool I always wished I had.

CI Sherlock is an open-source AI agent that plugs into GitHub Actions and runs after your Playwright tests. It reads the PR diff, correlates the failing tests with the files that actually changed, sends the whole picture to GPT-4o, and posts a plain-English root cause directly on the PR.

It also tracks flaky tests over time, flags slow tests worth splitting, and shows a release readiness score — so when management asks "are we good to ship?", there's an actual answer.

No server to run. No config file. Two env vars and one extra job in your workflow.

Turns out building the answer was better interview prep than reading about the problem.

github.com/slavkurochkin/ci-sherlock-agent

---
*Tip: use a screenshot of a real CI Sherlock PR comment as the post image.*
