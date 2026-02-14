class Clicker < Formula
  include Language::Python::Virtualenv

  desc "LLM-powered browser automation agent"
  homepage "https://github.com/spaceorc/clicker"
  head "https://github.com/spaceorc/clicker.git", branch: "master"
  license "MIT"

  depends_on "python@3.13"

  def install
    # Install directly using pip with all dependencies
    # This bypasses Homebrew's --no-deps restriction
    system "python3.13", "-m", "pip", "install", "--prefix=#{libexec}", "."

    # Create wrapper script
    (bin/"clicker").write_env_script libexec/"bin/clicker",
      PYTHONPATH: libexec/"lib/python3.13/site-packages",
      PATH:       "#{libexec}/bin:$PATH"
  end

  def post_install
    # Install Playwright browsers after package installation
    # Need to set PYTHONPATH because playwright is installed via pip --prefix
    ENV["PYTHONPATH"] = "#{libexec}/lib/python3.13/site-packages"
    system libexec/"bin/python", "-m", "playwright", "install", "chromium"
  end

  def caveats
    <<~EOS
      To get started, configure your API keys:

      1. Create config directory:
        mkdir -p ~/.config/clicker

      2. Create config file with your credentials:
        cat > ~/.config/clicker/config.env <<'EOF'
        # Google Vertex AI (for Anthropic via Vertex and Gemini)
        VERTEX_CREDENTIALS=<base64-encoded-service-account-json>
        VERTEX_PROJECT_NAME=my-project
        VERTEX_LOCATION=europe-west1

        # OpenAI (optional)
        OPENAI_API_KEY=sk-...
        OPENAI_BASE_URL=https://api.openai.com/v1
        EOF

      3. Secure the config file:
        chmod 600 ~/.config/clicker/config.env

      Alternative: You can also create .env file in your working directory.

      See .env.example in the clicker repository for more configuration options.

      Note: Playwright browsers (Chromium) are installed automatically.
    EOS
  end

  test do
    system "#{bin}/clicker", "--help"
  end
end
