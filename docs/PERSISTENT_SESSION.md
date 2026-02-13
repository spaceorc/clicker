# Persistent Browser Sessions

Clicker supports persistent browser profiles that preserve cookies, localStorage, and other session data between runs. This is useful when working with sites that require authentication.

## Quick Start

### Option 1: Using --pause flag (One-time login)

The simplest way to handle authentication:

```bash
# First run with --pause flag
make run-pause URL="https://example.com" SCENARIO="Navigate to dashboard"

# Browser will open, log in manually, then press Enter
# The session will continue but cookies won't persist after this run
```

### Option 2: Using --user-data-dir (Persistent cookies)

For persistent sessions across multiple runs:

```bash
# First run: authenticate manually
make run-pause \
  URL="https://example.com" \
  SCENARIO="Navigate to dashboard" \
  USER_DATA_DIR="./browser-profile"

# Browser opens, you log in manually, press Enter
# Session data is saved to ./browser-profile/

# Future runs: already authenticated!
make run-visible \
  URL="https://example.com" \
  SCENARIO="Check notifications" \
  USER_DATA_DIR="./browser-profile"

# No login needed - cookies are preserved!
```

## How It Works

When you specify `--user-data-dir`, Playwright uses `launch_persistent_context()` instead of the standard `launch()` + `new_context()` approach. This creates a persistent browser profile similar to your regular Chrome/Edge profile.

**What gets saved:**
- 🍪 Cookies (including authentication tokens)
- 📦 localStorage and sessionStorage
- 🔑 Indexed DB data
- 📝 Browser history
- ⚙️ Site permissions

**What doesn't get saved:**
- Open tabs (starts fresh each time)
- Downloads (session doesn't persist)

## Examples

### Example 1: LMS Automation

```bash
# Setup: One-time authentication
make run-pause \
  URL="https://myschool.edu/login" \
  SCENARIO="Log in to the system" \
  USER_DATA_DIR="./lms-profile"

# Login manually in the browser, press Enter when done

# Daily usage: Already authenticated
make run \
  URL="https://myschool.edu/courses" \
  SCENARIO="Complete today's quiz" \
  USER_DATA_DIR="./lms-profile"
```

### Example 2: Multiple Profiles

You can maintain separate profiles for different accounts:

```bash
# Work account
make run-visible \
  URL="https://app.com" \
  SCENARIO="Check work emails" \
  USER_DATA_DIR="./profiles/work"

# Personal account
make run-visible \
  URL="https://app.com" \
  SCENARIO="Check personal emails" \
  USER_DATA_DIR="./profiles/personal"
```

### Example 3: Testing with Resume

Combine persistent sessions with session resume:

```bash
# Start with persistent profile
make run-pause \
  URL="https://example.com" \
  SCENARIO="Complete multi-step task" \
  USER_DATA_DIR="./my-profile"

# If interrupted (Ctrl+C), resume from last step
make resume-last USER_DATA_DIR="./my-profile"
```

## Important Notes

### Security Considerations

⚠️ **WARNING:** The user data directory contains sensitive information including:
- Authentication cookies
- Session tokens
- Saved passwords (if any)
- Site data

**Best practices:**
1. **Never commit** user data directories to git
2. Add `browser-profile/` or `profiles/` to `.gitignore`
3. Keep user data directories in secure locations
4. Use separate profiles for different security contexts

### .gitignore

Add to your `.gitignore`:

```gitignore
# Browser profiles
browser-profile/
profiles/
*.profile/
```

### Headless Mode

Persistent context works with both headless and visible modes:

```bash
# Headless (default)
make run URL="..." SCENARIO="..." USER_DATA_DIR="./profile"

# Visible
make run-visible URL="..." SCENARIO="..." USER_DATA_DIR="./profile"
```

**Note:** First time setup with authentication should use visible mode (`--no-headless` or `make run-pause`) so you can log in manually.

### Profile Location

You can use:
- Relative paths: `./my-profile`, `../shared-profiles/work`
- Absolute paths: `/Users/yourname/.clicker-profiles/main`
- Environment variable: `$HOME/.clicker-profiles/default`

Example with environment variable:

```bash
export CLICKER_PROFILE="$HOME/.clicker-profiles/main"
make run-visible URL="..." SCENARIO="..." USER_DATA_DIR="$CLICKER_PROFILE"
```

## Troubleshooting

### Profile Corruption

If the browser fails to start or behaves strangely:

```bash
# Delete the corrupted profile
rm -rf ./browser-profile

# Start fresh
make run-pause URL="..." SCENARIO="..." USER_DATA_DIR="./browser-profile"
```

### Session Expired

If authentication expires despite using persistent context:

1. The site may have short-lived tokens (common for banking, high-security sites)
2. Use `--pause` flag to re-authenticate:

```bash
make run-pause URL="..." SCENARIO="..." USER_DATA_DIR="./existing-profile"
```

### Multiple Browser Instances

⚠️ **Cannot open the same profile in multiple browser instances simultaneously.**

If you get a "profile is in use" error:
- Close other instances using the same profile
- Use different profiles for parallel runs
- Wait for previous runs to complete

## Makefile Variables

```makefile
USER_DATA_DIR=./my-profile  # Path to browser profile directory
DEBUG=1                     # Enable verbose logging
```

Example:

```bash
make run-visible \
  URL="https://example.com" \
  SCENARIO="Do something" \
  USER_DATA_DIR="./profiles/main" \
  DEBUG=1
```
