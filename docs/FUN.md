# Fun / Cat Mode

The **Fun** tab makes the OS entertaining. **Cat Mode** meows using only
mechanisms the desktop itself provides — no listeners, no overlays, no
polling, nothing watching your clicks.

## What works where

| Trigger | How | Notes |
|---|---|---|
| Tab switch / buttons inside Enigmars Util | In-app `QMediaPlayer`, QtMultimedia first, `mpv/ffplay` fallback | Only while the app is open |
| Test Meow / Preview buttons | Same as above | Always play, even with Cat Mode off |
| Login sound (Plasma) | KDE `startkde` event → `~/.local/share/sounds/enigmars-fun/meow-login.oga` | Native event sound; next login |
| Logout sound (Plasma) | KDE `exitkde` event → `.../meow-logout.oga` | Native event sound; next logout |
| Login sound (other desktops) | `--meow-login` autostart entry | Fallback; auto-disabled when KDE sounds are on (avoids double meow) |
| Start Menu clicks, window switches, app launches | Not supported | No generic Wayland API; deliberately out of scope |

## Files

- Sources: `data/sounds/meow.mp3` (app), `meow-login.oga` / `meow-logout.oga` (KDE)
- Installed sounds ship under `/usr/share/enigmars-util/sounds/`
- Settings: `~/.config/enigmars-util/fun.json` (no root, user-level only)
- KDE overrides: `~/.config/plasma_workspace.notifyrc` (`[Event/startkde]` /
  `[Event/exitkde]` `Sound=` keys only — your theme is untouched)
- Installed event sounds: `~/.local/share/sounds/enigmars-fun/`

## Requirements

- `paplay`, `mpv`, or `ffmpeg` for previews and the non-Plasma login fallback.
- Plasma session for the login/logout event sounds.
- Event sounds must be enabled (System Settings → Notifications).

## Kill switch

Fun page → turn off Cat Mode and Disable KDE sounds, or:
`rm ~/.config/autostart/org.enigmars.Fun-Meow.desktop`
plus delete the `[Event/startkde]` / `[Event/exitkde]` `Sound=` lines or run
Disable on the Fun page.
