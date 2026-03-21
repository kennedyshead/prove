# Self-Hosted Runner Setup (macOS)

This guide covers setting up a Gitea Actions self-hosted runner on macOS for building proof binaries.

## Prerequisites

- macOS with Apple Silicon (M1/M2/M3/M4)
- Xcode Command Line Tools: `xcode-select --install`
- Python 3.11+ via Homebrew or pyenv

## Install the Gitea Runner

```bash
# Download the runner binary (check https://gitea.com/gitea/act_runner/releases for latest)
curl -sL https://gitea.com/gitea/act_runner/releases/download/v0.2.11/act_runner-0.2.11-darwin-arm64 -o act_runner
chmod +x act_runner
sudo mv act_runner /usr/local/bin/
```

## Register the Runner

1. Go to **Site Administration > Runners** (or your repository's **Settings > Actions > Runners**) on your Gitea instance.
2. Copy the registration token.
3. Register:

```bash
act_runner register \
  --instance https://code.botwork.se \
  --token YOUR_REGISTRATION_TOKEN \
  --name macos-arm64-runner \
  --labels self-hosted-macos-arm64
```

The label `self-hosted-macos-arm64` must match the `runs-on` value in the workflow matrix.

## Run as a Service

Create a launchd plist so the runner starts automatically:

```bash
cat > ~/Library/LaunchAgents/com.gitea.act_runner.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.gitea.act_runner</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/act_runner</string>
        <string>daemon</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USERNAME/.act_runner</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/act_runner.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/act_runner.err</string>
</dict>
</plist>
EOF

# Replace YOUR_USERNAME, then load:
launchctl load ~/Library/LaunchAgents/com.gitea.act_runner.plist
```

## Python Setup

The runner needs Python 3.11 for `setup-python`. Install via Homebrew:

```bash
brew install python@3.11
```

Or use pyenv if you manage multiple versions:

```bash
brew install pyenv
pyenv install 3.11
pyenv global 3.11
```

## Verify

1. Check the runner appears as **Online** in Gitea's runner list.
2. Push a test tag to trigger the release workflow:
   ```bash
   git tag v1.1.0-rc1
   git push origin v1.1.0-rc1
   ```
3. Confirm both `linux-x86_64` and `macos-aarch64` jobs run.

## Enable macOS Builds

Once the runner is verified, uncomment the macOS matrix entry in `.gitea/workflows/release.yml`:

```yaml
- os: self-hosted-macos-arm64
  platform: macos-aarch64
```
