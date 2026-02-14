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

  def caveats
    <<~EOS
      After installation, install Playwright browsers:
        #{libexec}/bin/playwright install chromium

      Or use the make command:
        make install  # from clicker source directory
    EOS
  end

  test do
    system "#{bin}/clicker", "--help"
  end
end
