# Go Public — Iteration 0 manual steps

Everything in the repo is built and passing locally. These are the steps only you can do
(they need your accounts and a payment method). Doing them completes Iteration 0's Verify gate
and, critically, **starts the 6-month JOSS clock the moment the repo is public.**

## 1. Create the GitHub repo and make it public

```bash
cd "US datascience projects/truewise"
git remote add origin git@github.com:<your-username>/truewise.git
git push -u origin main
```

Then on GitHub: Settings → General → Danger Zone is not needed; just create the repo as
**Public** when you make it (or flip it to Public if you created it private). Making it public
is what starts the JOSS eligibility clock, so do this early even though it is bare.

After pushing, confirm the **CI** workflow runs green on the Actions tab.

## 2. Register truewise.us

- Registrar: **Cloudflare Registrar** (at-cost, ~$5–10/yr) or Namecheap.
- `.us` requires a **US nexus attestation** at checkout (US citizen/resident/org). You qualify;
  just select the standard nexus category.
- Budget is capped ~$50/yr, so `.us` is the intended choice (not `.io`).

## 3. Connect Cloudflare Pages (auto-deploy)

- Cloudflare dashboard → Pages → Create a project → Connect to your GitHub `truewise` repo.
- Build settings: **Framework preset = None**, **Build command = (leave empty)**,
  **Build output directory = `site`**. The site is static, so there is no build step yet.
- Set the production branch to `main`. Every merge to `main` then auto-deploys `site/`.
- Add the custom domain `truewise.us` in the Pages project (Cloudflare handles DNS + HTTPS).

The `deploy` job in `.github/workflows/ci.yml` is a placeholder note — Cloudflare Pages
deploys directly from the repo, so you do not need a deploy token unless you later prefer to
push from Actions. Keep whichever one you wire up.

## 4. Verify gate (Iteration 0 done when all true)

- [ ] `https://truewise.us` loads over HTTPS from a clean/incognito browser.
- [ ] A test commit to `main` auto-deploys within minutes and is visible live.
- [ ] Repo is publicly visible while `data/` stays untracked (check the file list on GitHub).
- [ ] `docs/IMPACT_LOG.md` updated: repo public (date), domain registered (date), first deploy (date).

## Notes

- Keep `data/` and `.env` out of git — already handled by `.gitignore`.
- License: code is MIT (`LICENSE`); the published **dataset** will be CC-BY (added at the first
  data release in Iteration 1).
