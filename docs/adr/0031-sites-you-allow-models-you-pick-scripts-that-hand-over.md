# 0031. Sites you allow, the model you pick, page scripts that hand over

**Status:** Accepted, 2026-10-28. Amends [0029](0029-a-chrome-extension-for-notebooks.md) (sites)
and [0030](0030-fix-notebook-errors-through-a-desktop-helper.md) (model).

## Context
Using the extension on a real cluster turned up three problems:
- **Apply hung** after the extension was removed and loaded again. Chrome leaves MAIN-world
  scripts running when an extension goes. The new page script saw the old one's "already
  started" marker (`true`) and stood aside; the old script didn't know about edits, so Apply
  waited forever.
- **The model was fixed** to whatever Marginalia's Settings said, with no way to choose in the panel.
- **Sites were hardcoded** to UMD's domain and localhost, in the permissions and in the copy.

## Decision
- **Page scripts hand over.** Each one leaves `{ version, stop }` on the page; a newer one stops
  its predecessor before starting (`claimPage`). Every page message carries the page script's
  version (`PAGE_SCRIPT`), so replies from any other version fail validation and are dropped. An
  edit that gets no answer in 6 s fails with "Reload the tab, then try again" instead of waiting.
- **The model is picked in the panel.** The helper lists Claude's models with `hello`; the
  status bar has a menu; the choice is remembered in the browser (`storage.local`) and sent with
  each fix. The helper accepts only models it listed. Marginalia's own setting is left alone.
  Each proposal says which model made it.
- **Sites are yours.** `localhost` and `127.0.0.1` (Jupyter on this computer or through an SSH
  tunnel) are one click. Any other address is typed in, and Chrome asks about that one host.
  `optional_host_permissions` lists `http://*/*` and `https://*/*` only so Chrome *can* ask;
  nothing is granted until you allow a site.

## Consequences
- A tab still running the very first page script (which left `true`) gets the new script
  alongside it; the old one's replies are ignored. Reloading the tab clears it.
- People on a hosted JupyterHub add its address once; the panel shows the form whenever a tab
  can't be read.
