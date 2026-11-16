# Platform access, recording and clip rights

This project is designed for creator-authorised recording and reuse.

- A publicly viewable stream is not automatically licensed for downloading, editing, reposting or monetisation.
- Obtain the creator's permission or use footage from a channel/account for which you are the broadcaster or an authorised editor.
- Use Twitch's official API for clips from a broadcaster's VOD when the required broadcaster/editor authorisation and OAuth scopes are available. The Twitch API documents a 5–60 second clip duration and requires the appropriate clip-management permission.
- Do not bypass login, subscriptions, DRM, geo-restrictions, access controls, or platform rate limits.
- Do not use this project to capture private streams or content that the account is not entitled to access.
- Do not assume fair use applies. Copyright exceptions are fact-specific and vary by jurisdiction. Commentary, criticism and transformative editing do not guarantee that a use is lawful or that a platform will not issue a claim.
- Keep a record of permission, licence terms, source URL, creator/channel, capture time and permitted platforms for each clip.
- Do not publish automatically. Review context, attribution requirements, music rights, privacy and platform rules before posting.
- Store Twitch OAuth tokens in local environment variables or a secret manager. Never commit tokens, cookies or signed media URLs.

The CLI requires an explicit `--confirm-rights` acknowledgement and an authorised direct media URL. That acknowledgement is an operational safeguard, not legal advice or proof of permission.
