# Release pipeline (parked)

`release.yml` tests the code, builds the stand-alone MarkerPilot app for Linux, Windows and macOS, runs the self-test on each build, and publishes a GitHub release when a `v*` tag is pushed.

It lives here because the GitHub login used to create this repo had no `workflow` permission. To switch it on:

```bash
gh auth refresh -s workflow
mkdir -p .github/workflows && git mv ci/release.yml .github/workflows/release.yml
git commit -m "Enable release pipeline" && git push
git tag v2.0.1 && git push origin v2.0.1
```
