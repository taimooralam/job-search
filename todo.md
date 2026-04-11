# TODO

## 2026-03-30
- [ ] Re-enable scout selector cron on VPS (Claude CLI usage resets Mar 30, 12pm UTC)
  ```bash
  ssh root@72.61.92.76 "crontab -l | sed 's/^#DISABLED-USAGE: //' | crontab -"
  ```
- [ ] Retry the 14 failed queue items after usage resets
- [ ] Update OpenAI API key on VPS (fallback path is broken — 401 invalid key)
