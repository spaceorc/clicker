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
