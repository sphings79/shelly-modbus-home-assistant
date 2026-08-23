**Subject:** Social preview image uploads succeed but are never served (404) — and "Remove image" has no effect

Hi,

The social preview for my public repository **sphings79/shelly-modbus-home-assistant** (repository id `1343672068`, created 2026-08-23) cannot be set. Uploads complete successfully, GitHub records that a custom image exists, but the image URL always returns 404. Removing the image does not work either, so the repository is now stuck with a broken social preview.

**Effect:** `og:image` and `twitter:image` on the repo page point at a URL that 404s, so link previews on Slack, Discord, WhatsApp and Mastodon render nothing at all. This is worse than having no custom image, since the auto-generated card is suppressed.

### The upload itself succeeds

Network trace of a full upload from the Settings → General → Social preview form:

```
POST https://github.com/upload/policies/repository-images          -> 201
POST https://github-production-repository-image-32fea6.s3.amazonaws.com/  -> 204
PUT  https://github.com/upload/repository-images/1968801           -> 200
```

Nothing is blocked or rejected. GitHub then reports a custom image is in place:

```
$ gh api graphql -f query='{repository(owner:"sphings79",name:"shelly-modbus-home-assistant"){usesCustomOpenGraphImage openGraphImageUrl}}'
{
  "data": {
    "repository": {
      "usesCustomOpenGraphImage": true,
      "openGraphImageUrl": "https://repository-images.githubusercontent.com/1343672068/a9a440bc-478d-46a0-b924-35ef1f1542ea"
    }
  }
}
```

### But the image is never served

```
$ curl -sI "https://repository-images.githubusercontent.com/1343672068/a9a440bc-478d-46a0-b924-35ef1f1542ea"
HTTP/2 404
content-type: text/html
x-ms-error-code: WebContentNotFound
x-cache: MISS
age: 0
```

`x-cache: MISS` with `age: 0` confirms this is not a cached negative response — it comes straight from origin. Polled every 25 seconds for over 10 minutes: consistently 404. A first upload made ~3 hours earlier is still 404, so this is not propagation delay.

The image slot is also **not** empty from GitHub's point of view: the Settings page preview box renders blank after a hard reload, and every new upload allocates a fresh UUID that 404s the same way.

### "Remove image" does not work either

Clicking Settings → Social preview → Edit → **Remove image** does not clear the setting. `usesCustomOpenGraphImage` stays `true` and the same 404 URL is still returned. The page also hangs on submit. This is what makes the state unrecoverable from my side.

### What I have already ruled out

| Variable | Tested |
|---|---|
| Browser | Chrome and Safari |
| Network | Home broadband and mobile data |
| Browser extensions | Upload trace above shows nothing blocked |
| File format | PNG and JPEG |
| File size / dimensions | 1280×640 @ 97 KB, 1280×640 @ 96 KB, 640×320 @ 20 KB |
| Repository visibility | public, not archived, not disabled, not a template |
| GitHub status page | "All Systems Operational" throughout |

Five upload attempts across two browsers and two networks, each producing a new UUID that 404s.

### What I am asking for

1. Please clear the broken social preview record for repository `1343672068`, so the auto-generated card is used again.
2. If possible, identify why images uploaded for this repository are accepted but never written to `repository-images.githubusercontent.com`.

Happy to provide further traces, request IDs or timestamps. One Azure request id from a failing fetch: `e0efda5a-301e-0000-51f8-329884000000`.

Thanks!
