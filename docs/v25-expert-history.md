# V25 – Expert History Engine
Read-only statistical audit. Initial goal: 52 prior coupons, 100 source identities, 10,000 observations; not a completion claim.
- Recovered articles: 4977 (26), 4978 (26), 4979 (37); 4980 imported from V24, excluding untimed/postclose-page evidence.
- Poolarn 4979 positions 9 and 10 excluded because the explicit large system lists different opponents from the official coupon.
- Recovered article timestamps are not independent proof of original unedited content. Keep retrospective and prospectively frozen results separate.
- For older rounds only official results may be present; never reconstruct historical market odds from present-day prices.
- First choices and system coverage are descriptive. Fractional hits discount hedges. Only human result picks enter fixed-weight experiment, with one vote per publisher group.
- Do not choose a weight on this pilot. Once sufficient preclose odds and match outcomes exist, fit on earlier rounds and evaluate on later unseen rounds, using identical matched samples and Brier/log loss; benchmark the existing form model separately.
- No scraped content or automated external collector; manually verify dates, team pairs, type and source.
- Run: `python -m scripts.v25_history --outdir data`; tests: `python -m unittest tests.test_v25_history`.
