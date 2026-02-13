# GitHub Secrets Configuration

To run integration tests in GitHub Actions, you need to configure the following repository secrets.

Go to: **Settings → Secrets and variables → Actions → New repository secret**

## Required Secrets

### 1. `VERTEX_PROJECT_NAME`

Your Google Cloud Project ID (or project name) that has Vertex AI API enabled.

**Example:**
```
my-project-123456
```

**How to find:**
```bash
gcloud config get-value project
```

### 2. `VERTEX_CREDENTIALS`

**Base64-encoded** Google Cloud service account JSON credentials.

**How to create:**

1. Go to Google Cloud Console → IAM & Admin → Service Accounts
2. Create a service account (or use existing)
3. Grant roles:
   - `Vertex AI User` (for Anthropic/Gemini API)
   - `Service Account Token Creator` (if needed)
4. Create a JSON key for the service account
5. Download the JSON file
6. **Base64-encode the JSON file:**

   ```bash
   # On macOS/Linux:
   base64 -i your-service-account-key.json | tr -d '\n'

   # On Windows (PowerShell):
   [Convert]::ToBase64String([IO.File]::ReadAllBytes("your-service-account-key.json"))
   ```

7. Copy the **base64-encoded string** into this GitHub secret

**IMPORTANT:** The value should be a single long base64 string with no line breaks.

## Optional Secrets (if using OpenAI)

### 3. `OPENAI_API_KEY`

Your OpenAI API key (starts with `sk-`).

Only needed if you want to run tests with OpenAI models.

## Verifying Setup

After adding secrets, the GitHub Actions workflow will:
- Run unit tests on every push/PR (free, fast)
- Run integration tests only on master branch pushes (costs ~$0.05 per run)
- Can manually trigger integration tests from the Actions tab

## Cost Considerations

- **Unit tests:** Free (no API calls)
- **Integration tests:** ~$0.05 per run (3 tests × ~$0.02 each)
- **Typical monthly cost:** Variable, depends on commit frequency

To reduce costs, integration tests only run:
- On pushes to master branch (when actual code changes)
- When manually triggered (workflow_dispatch)

PRs only run unit tests by default.
