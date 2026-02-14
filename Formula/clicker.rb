class Clicker < Formula
  include Language::Python::Virtualenv

  desc "LLM-powered browser automation agent"
  homepage "https://github.com/spaceorc/clicker"
  head "https://github.com/spaceorc/clicker.git", branch: "master"
  license "MIT"

  depends_on "python@3.13"

  def install
    # Create virtualenv and install dependencies
    virtualenv_install_with_resources

    # Install Playwright browsers
    system libexec/"bin/playwright", "install", "chromium"
  end

  test do
    system "#{bin}/clicker", "--help"
  end
end
