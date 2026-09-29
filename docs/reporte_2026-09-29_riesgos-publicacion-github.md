# Risk report: publishing youtube-digest on GitHub

- **Date:** 2026-09-29
- **Author:** ZCode session (research commissioned by William)
- **Scope:** risks of making this repository public, with mitigations applied

## Summary

Publishing the code is low risk if two hard rules hold: never commit `.env`
(the Gemini API key) and never commit `data/` (digests that reproduce
third-party video content plus the owner's viewing history). The tool itself
does not download videos or circumvent any technical protection measure; it
feeds public YouTube URLs to Gemini through a documented, official API
feature, which puts it in a different category than downloaders such as
yt-dlp.

## Detail

### 1. Gemini API key leakage (highest practical risk)

The 2026 context makes this worse than it used to be: Google enabled Gemini
access by default on existing Google API keys, so keys committed years ago
as "non-secrets" became billable. Truffle Security documented the shift
(Feb 2026) and Zuplo reported over 3,000 exposed keys affected and one $82K
bill case (Mar 2026). A user on Google's own forum reported ~$10K in charges
in under two hours from a compromised AI Studio key (May 2026). Bots scan
GitHub for keys within minutes of a push.

Mitigations in place:

- Key lives only in `.env` (gitignored, chmod 600); never hardcoded, never
  copied into the global ZCode config entry.
- GitHub enables secret scanning with push protection by default on public
  repos since 2024: a detected key blocks the push, and Google now
  auto-blocks keys it detects as leaked and used against the Gemini API.
- Recommended for the owner: budget alerts in AI Studio, and optionally
  gitleaks as a pre-commit hook.

### 2. Copyright of the digested content

Two cases must be kept separate:

- **The code.** It does not download, mirror or deprotect anything. Passing a
  public YouTube URL as a `file_data` Part is a documented Gemini API
  capability (ai.google.dev/gemini-api/docs/video-understanding). Google
  consumes Google-hosted content through the channel Google designed.
- **The data.** `data/digests.db` and the `data/digests/*.md` mirrors
  reproduce, in text, the content of videos owned by third parties.
  Publishing them would be redistributing protected material. The Gemini API
  terms also grant output ownership while prohibiting uses that infringe
  third-party rights.

Mitigation: `data/` is fully gitignored. The repo ships the mill, not the
flour.

### 3. DMCA precedent against YouTube tools

Verified history: the RIAA obtained a takedown of youtube-dl from GitHub in
October 2020 under DMCA section 1201 (circumvention of the "rolling cipher");
GitHub reinstated it in November 2020 after EFF intervention, and yt-dlp
remains hosted on GitHub today. Pressure on downloader projects continued
through 2025-2026 (technical countermeasures such as PoToken and SABR).
Reports of a 2025 YouTube DMCA subpoena against GitHub users could not be
verified in this research and are not treated as fact.

This project has a materially different profile: no download, no contact with
YouTube's infrastructure, consumption through an official Google API
feature. A takedown is unlikely; if one arrived anyway, the youtube-dl
precedent shows GitHub tends to reinstate repos facing DMCA abuse.

### 4. Repository hygiene

The working directory contained local artifacts from other tooling
(`.auth/`, `.v2c/`, `.video_agent/`). A careless `git add .` would publish
them. Mitigation: a strict `.gitignore` was written before `git init`, and
`git status` was reviewed before the first commit.

### 5. Privacy

The digest database doubles as a viewing-history record (what was watched,
when, how often). An additional reason, beyond copyright, to keep `data/`
out of any public repo.

### 6. Licensing and responsibility to third parties

Without a LICENSE file the repo defaults to all rights reserved, so nobody
could legally reuse the code; the repo now ships MIT. Anyone installing this
MCP server brings their own API key and operates under their own terms of
service; the README states this explicitly along with a non-affiliation
note. The code was ported from a private project owned by the same author,
so there is no third-party licensing conflict.

## Conclusions

1. Publishable with low residual risk, provided `.env` and `data/` never
   enter git history. Both are covered by `.gitignore` plus GitHub's default
   push protection as a safety net.
2. The legal exposure of the code itself is low because there is no
   downloading and no circumvention; the Gemini-by-URL path is an official,
   documented feature.
3. The one thing that would change this assessment: committing stored
   digests of third-party videos. That is the only material in this repo
   whose publication would create a real copyright problem.

## Sources

- Truffle Security, "Google API keys weren't secrets. But then Gemini" (Feb 2026)
- Zuplo, "3000 Google API keys just got a lot more dangerous" (Mar 2026)
- Google AI developers forum, compromised key with ~USD 10K in charges (May 2026)
- GitHub Blog, "Secret scanning and push protection are enabled by default" (Mar 2024)
- GitGuardian, "GitHub push protection: benefits and key limitations" (Jul 2025)
- GitHub Blog, "Standing up for developers: youtube-dl is back" (Nov 2020)
- EFF, "GitHub reinstates youtube-dl after RIAA's abuse of DMCA" (Nov 2020)
- TorrentFreak, RIAA takedown coverage (Oct 2020)
- Google, Gemini API video understanding documentation (YouTube URL input)
