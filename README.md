Mise config
===========

Mise configuration, auto-synced using mise dot

## Bootstrapping

This repository can be used to bootstrap a new machine by following these steps:

- Install mise: https://mise.jdx.dev/getting-started.html#installing-mise-cli
- First run: `mise bootstrap --adopt https://github.com/mortenlj/mise-config.git`
- After installing bitwarden, you must log in and enable ssh-agent before cloning repositories will work
  - For Linux, see below

### Flatpak and Bitwarden on Linux

Mise will install flatpak, but fail installing Bitwarden because flathub is not defined.
We need to add flathub, and retry:

- Add flathub to flatpak: `flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo`
- Run bootstrap again: `mise bootstrap`
