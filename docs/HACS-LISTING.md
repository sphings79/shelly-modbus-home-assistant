# Getting listed in HACS

Two separate submissions, in this order. Only the first is required to appear in HACS.

| Step | Repository | Purpose | Required? |
|---|---|---|---|
| 1 | `hacs/default` | Makes the integration appear in HACS without adding a custom repository | **Yes** |
| 2 | `home-assistant/brands` | Shows the icon inside Home Assistant itself | Optional |

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

## Step 2 — `home-assistant/brands` (icon inside Home Assistant)

Not needed for the HACS listing: HACS is already satisfied by the `brand/` folder in this
repository. Do this so Home Assistant shows the icon on the Devices & Services page.

1. Fork <https://github.com/home-assistant/brands>.

2. Add exactly these two files:

   ```
   custom_integrations/shelly_modbus/icon.png       256x256
   custom_integrations/shelly_modbus/icon@2x.png    512x512
   ```

   Prepared, brands-compliant copies (interlaced, optimised, transparent) are ready to
   drop in — see the note below.

3. Open the PR.

**Submit the icons only, not the logo.** The brands rules state that custom integrations
"must not use Home Assistant branded images, as this might confuse the end-user into
thinking that the integration is an internal/official integration". This repository's
`logo.png` carries the wording *"for Home Assistant"* and would be rejected on that basis.
The icons contain no Home Assistant branding and are fine.

Once merged, the icon is served from
`https://brands.home-assistant.io/shelly_modbus/icon.png`.

---

## Meanwhile

Until the `hacs/default` PR is merged, anyone can already install the integration by
adding this repository as a **custom repository** in HACS — see the README.
