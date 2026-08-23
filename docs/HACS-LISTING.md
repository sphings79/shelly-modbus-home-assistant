# Getting listed in HACS

One submission. The icon is already handled inside this repository.

| Step | Repository | Purpose | Status |
|---|---|---|---|
| 1 | `hacs/default` | Makes the integration appear in HACS without adding a custom repository | [PR #10260](https://github.com/hacs/default/pull/10260) |
| 2 | `home-assistant/brands` | — | **Not applicable any more**, see below |

---

## Prerequisites — already met

The HACS Action reports **all 9 checks passed** on `main`:

```
<Validation brands> completed          <Validation topics> completed
<Validation description> completed     <Validation license> completed
<Validation archived> completed        <Validation issues> completed
<Validation information> completed     <Validation hacsjson> completed
<Validation integration_manifest> completed
All (9) checks passed
```

Plus everything else HACS asks for:

- [x] Public GitHub repository
- [x] HACS Action passing with no errors and no ignores
- [x] Hassfest Action passing
- [x] A real GitHub release (`v1.0.0`), not just a tag
- [x] Repository description set
- [x] Repository topics set
- [x] Issues enabled
- [x] `hacs.json` present
- [x] Brand assets under `custom_components/shelly_modbus/brand/`
- [x] Works when added as a custom repository

Only the repository **owner or a major contributor** may submit the PR — that is you.

---

## Step 1 — `hacs/default` (this is the actual listing)

1. Fork <https://github.com/hacs/default> and branch off `master`.

2. Open the file `integration` (no extension, JSON array) and insert this line
   **in alphabetical order**:

   ```json
   "sphings79/shelly-modbus-home-assistant",
   ```

   It belongs exactly here:

   ```
     "spezzuti/backup-monitor",
     "sphings79/shelly-modbus-home-assistant",   <-- insert
     "spiri439/himoinsa-c4lan",
   ```

   Sorting is checked automatically and is case-insensitive.

3. Open the PR against `hacs/default`. Fill in the template honestly and completely —
   incomplete submissions are closed straight away. Make sure **"Allow edits from
   maintainers"** stays ticked, which means submitting from a personal account, not an
   organisation.

4. Automated checks run on the PR: manifest validation, HACS validation, brand
   verification, repository activity, release presence, ownership, JSON formatting and
   alphabetical order.

After the merge the repository is picked up in the next scheduled scan — it does not
appear instantly.

---

## Step 2 — not needed

`home-assistant/brands` **no longer accepts pull requests for custom integrations**. Its
pull request template states this outright, pointing at the
[Brands Proxy API announcement](https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api).

Since Home Assistant 2026.3, a custom integration ships its own brand images in a `brand/`
subdirectory, which Home Assistant serves through `/api/brands/integration/{domain}/{image}`.
Local images take priority over the brands CDN, and no manifest entry is required.

This repository already has exactly that:

```
custom_components/shelly_modbus/brand/
├── icon.png        256x256
├── icon@2x.png     512x512
├── logo.png
└── logo@2x.png
```

So the icon shows up in Home Assistant with nothing further to do.

---

## Meanwhile

Until the `hacs/default` PR is merged, anyone can already install the integration by
adding this repository as a **custom repository** in HACS — see the README.
